#!/usr/local/bin/python3
from nmigen import *
from nmigen.cli import main
from nmigen.back import pysim, verilog

from nmigen_boards.icebreaker import ICEBreakerPlatform

# N   X [cond]    start  rdy  avail | next_N  next_X  || notes
# ----------------------------------+-----------------++---------------------------------
# ...                               |                 ||
# dc  dc                 1    A     |                 || A: avail=0 after rst, and 1 after last computation
# dc  dc          1      0    0     |                 || load ld_X into X and start computations (strobe)
# 1   ld_X (>0)   dc     0    0     |                 ||
# ...                               |                 ||
# n    >1 & even  dc     0    0     | n+1     n / 2   || (shr via wires)
# n    >1 & odd   dc     0    0     | n+1     3n+1    || (== 2n+1+n == shl and set lsb, then add n)
# ...                               |                 ||
# n   ==1         dc     1    1     | n       n/a     || N unchanged from here on, until next load strobe
# ...
# next load cycle

# TODO:
#   - out of range error
#       - for odd number, always need 2 more bits left (i.e. factor of 4), otherwise flag overflow
#   - cycles exhausted error
#       - mostly needed since the RAM to record the sequence is limited
#   - improve effort
#       - do not start even numbers (they will reduce to 1)
#       - pre-compute the first couple of steps:
#           a) odd number = 2n+1
#           b) first precomputed step (odd):  3m+1 -> 3(2n+1)+1 = 6n+3+1 = 6n+4 = 2(3n+2) -> i.e. even
#           c) 2nd   precomputed step (even): 2(3n+2) -> 3n+2, which may be odd or even
#                     init   step1        step2 
#                - e.g.  3   -> 9+10 = 10 ->  5 (odd)
#                -       5   -> 15+1 = 16 ->  8 (even)
#                -      11   -> 33+1 = 34 -> 17 (odd)
class Collatz(Elaboratable):
    def __init__(self, xwidth, nwidth):
        # interface, input
        self.rdy    = Signal()
        self.done   = Signal()
        self.out    = Signal(2*xwidth)
        self.err_x  = Signal() # overflow
        self.err_n  = Signal() # counter exhausted

        # interface, input
        self.ld_x    = Signal(xwidth)
        self.start   = Signal()

        # current state
        self.x      = Signal(2*xwidth)
        self.n      = Signal(nwidth)

        # next state
        self.next_x = Signal(2*xwidth)
        self.next_n = Signal(nwidth)

        # internal, helpers
        self.mem = Memory(width=xwidth, depth=(1 << nwidth))
        self.nmax = (1 << nwidth) - 1 # e.g. 4 bit -> nmax = 15
        
    def elaborate(self, platform):
        m = Module()
        m.submodules.wrport = wrport = self.mem.write_port()
        
        # load
        with m.If(self.start):
            m.d.sync += [
                self.x.eq(self.ld_x),
                self.n.eq(0),
                self.err_x.eq(0),
                self.err_n.eq(0)
            ]
        # drive computation
        with m.Else():
            with m.If(self.x > 1):
                m.d.sync += [
                    self.x.eq(self.next_x),
                    self.n.eq(self.next_n)
                ]
            with m.Else():
                m.d.comb += [
                    # output
                    self.out.eq(self.n),
                ]
            m.d.comb += [
                # record x in RAM (last entry to record 1 itself, optional?)
                wrport.addr.eq(self.n),
                wrport.data.eq(self.x),
                wrport.en.eq(1)                    
            ]
                
        # rdy, is 1 upon reset and after computations
        with m.If( (self.x == 0) | (self.x == 1) ):
            m.d.comb += [
                self.rdy.eq(1) # true after reset and end of compute
            ]
        with m.Else():
            m.d.comb += [
                self.rdy.eq(0)
            ]

        # done, is not high after reset, but only after computation
        # makes it easier to use 'done' as the .we signal to write into
        # result memory (whereas using rdy would have lead to a stray
        # initial write, _before_ the first computation)
        with m.If(self.x == 1):
            m.d.comb += [
                self.done.eq(1) # not true after reset, only after compute
            ]
        with m.Else():
            m.d.comb += [
                self.done.eq(0)
            ]
            
        with m.If(self.n < self.nmax-1):
            with m.If(self.x[0]):
                # odd
                # check for risk of overflow, self.x needs to be at least a
                # factor of 4 below max(self.x.nbits, i.e. xwidth),
                # i.e. most significant two bits of self.x not set!
                with m.If( (self.x[self.x.nbits-1] == 0) & (self.x[self.x.nbits-2] == 0) ):
                    m.d.comb += [
                        # TODO: write this as <<1 (shr), set lsb, +self.x
                        self.next_x.eq( (3*self.x + 1) >> 1),
                        self.next_n.eq(self.n + 2)
                    ]
                with m.Else():
                    # overflow
                    m.d.comb += [
                        self.next_x.eq(1), # stop sequence, will lead to done!
                    ]
                    m.d.sync += [
                        self.err_x.eq(1)
                    ]                
            with m.Else():
                # even
                m.d.comb += [
                    self.next_x.eq(self.x >> 1), # shr as a way to "div2"
                    self.next_n.eq(self.n + 1)
                ]
        with m.Else():
            # sequence length exhausted
            m.d.comb += [
                self.next_x.eq(1), # stop sequence, will lead to done!
            ]
            m.d.sync += [
                self.err_n.eq(1)
            ]
        return m

if __name__ == "__main__":
    collatz = Collatz(32, 10)
    print(verilog.convert(collatz, ports=[collatz.ld_x, collatz.start, collatz.rdy]))
    #print(verilog.convert(collatz, ports=[]))

    with pysim.Simulator(collatz,
                         vcd_file=open("collatz.vcd", "w"),
                         gtkw_file=open("collatz.gtkw", "w"),
                         traces=[collatz.ld_x, collatz.start, collatz.rdy]) as sim:
        sim.add_clock(100e-9)

        def collatz_proc():
            # ---------
            yield collatz.ld_x.eq(1)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (0)

            # ---------
            yield collatz.ld_x.eq(2)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (1)
            
            # ---------
            yield collatz.ld_x.eq(3)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (7)

            yield collatz.ld_x.eq(5)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (5)

            yield collatz.ld_x.eq(11)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (14)


            yield collatz.ld_x.eq(27)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (111)


            yield collatz.ld_x.eq(97)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (118)


            yield collatz.ld_x.eq(871)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (178)

            yield collatz.ld_x.eq(6171)
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            print('%s %s %s' % (r,x,n))
            assert (n) == (261)
            
        sim.add_sync_process(collatz_proc())
        sim.run_until(100e-6, run_passive=True)
        print('* Passed positive test cases.')

    collatz = Collatz(32,6) # nwidth too small (6), expect err_n to be raised
    with pysim.Simulator(collatz,
                         traces=[collatz.ld_x, collatz.start, collatz.rdy]) as sim:
        sim.add_clock(100e-9)

        def collatz_proc():
            # ---------
            yield collatz.ld_x.eq(6176) # sequence length is 261, need 9 bits, giving it only 6
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            err_n=yield collatz.err_n
            print('%s %s %s %s' % (r,x,n,err_n))
            assert (err_n) == (1)
        sim.add_sync_process(collatz_proc())
        sim.run_until(100e-6, run_passive=True)
        print('* Passed err_n test.')

    collatz = Collatz(13,10) # 13 bit xwidth too small (needs 14), expect err_x to be raised
    with pysim.Simulator(collatz,
                         traces=[collatz.ld_x, collatz.start, collatz.rdy]) as sim:
        sim.add_clock(100e-9)

        def collatz_proc():
            # ---------
            yield collatz.ld_x.eq(27) # higest x in sequence would be 9232, needs 14 bits
            yield collatz.start.eq(True)
            yield
            yield collatz.start.eq(False)
            yield

            r = yield collatz.rdy
            cnt = 0
            while not r == 1:
                yield
                r = yield collatz.rdy
                cnt = cnt + 1
            print('cycle counter = %d' % cnt)

            r=yield collatz.rdy
            x=yield collatz.x
            n=yield collatz.n
            err_x=yield collatz.err_x
            print('%s %s %s %s' % (r,x,n,err_x))
            assert (err_x) == (1)
        sim.add_sync_process(collatz_proc())
        sim.run_until(100e-6, run_passive=True)
        print('* Passed err_x test.')

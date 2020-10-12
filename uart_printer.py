from nmigen import *
from nmigen.back import pysim, verilog
from nmigen.cli import main
from nmigen.lib.fifo import *
from nmigen_boards.icebreaker import ICEBreakerPlatform

from bcd import BCD1_32

import argparse

maxn = len(Const(9999999999)) # single digit billions, needs 34 bits

class Hex8Decoder(Elaboratable):
    def __init__(self):
        self.i = Signal(8)
        self.o_lower = Signal(8)
        self.o_upper = Signal(8)

        self.lower = Signal(4)
        self.upper = Signal(4)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += Cat(self.lower, self.upper).eq(self.i)
        with m.If(self.lower <= 9):
            m.d.comb += self.o_lower.eq(self.lower + ord('0'))
        with m.Else():
            m.d.comb += self.o_lower.eq(self.lower + (ord('a') - 10))
        with m.If(self.upper <= 9):
            m.d.comb += self.o_upper.eq(self.upper + ord('0'))
        with m.Else():
            m.d.comb += self.o_upper.eq(self.upper + (ord('a') - 10))
        return m

class UART_Printer(Elaboratable):
    def __init__(self, uartfifo):
        # write interface
        self.we = Signal()
        self.din = Signal(3+maxn)
        self.writable = Signal()
        # destination uart fifo
        self.uartfifo = uartfifo # uart to host fifo

        # internal state
        self.inputfifo = SyncFIFOBuffered(width=3+maxn, depth=128)
        # helpers
        self.cmd  = Signal(3)
        self.data = Signal(maxn)
        # decimal printing
        self.nonlead0 = Signal()
        self.bcd1 = BCD1_32()
        # verbatim printing
        self.va = Signal(8)
        self.vb = Signal(8)
        self.vc = Signal(8)
        self.vd = Signal(8)
        # hex printing
        self.h_1a = Signal(8)
        self.h_1b = Signal(8)
        self.h_1c = Signal(8)
        self.h_1d = Signal(8)
        self.h8d_1 = Hex8Decoder()
        self.h8d_2 = Hex8Decoder()
        self.h8d_3 = Hex8Decoder()
        self.h8d_4 = Hex8Decoder()
        self.h_spaceout = Signal()

    def elaborate(self, platform):
        m = Module()
        m.submodules.bcd1 = self.bcd1
        m.submodules.h8d_1 = self.h8d_1 # high order byte
        m.submodules.h8d_2 = self.h8d_2
        m.submodules.h8d_3 = self.h8d_3
        m.submodules.h8d_4 = self.h8d_4
        m.d.comb += self.h8d_1.i.eq(self.h_1a) # high order byte
        m.d.comb += self.h8d_2.i.eq(self.h_1b)
        m.d.comb += self.h8d_3.i.eq(self.h_1c)
        m.d.comb += self.h8d_4.i.eq(self.h_1d)

        m.submodules.inputfifo = self.inputfifo
        m.d.comb += [
            self.inputfifo.w_en.eq(self.we),
            self.inputfifo.w_data.eq(self.din),
            self.writable.eq(self.inputfifo.w_rdy)
        ]
        with m.FSM(reset='READY') as fsm:
            with m.State('READY'):
                with m.If( (self.inputfifo.r_rdy) & (self.uartfifo.w_rdy) ):
                    m.d.comb += [
                        # cmd are the high order bits
                        Cat(self.data, self.cmd).eq(self.inputfifo.r_data), #s
                        # remove input element
                        self.inputfifo.r_en.eq(1),
                    ]
                    m.d.sync += [
                        self.nonlead0.eq(0),
                    ]
                    # command dispatcher
                    with m.Switch(self.cmd):
                        with m.Case(4): # b100, VERBATIM
                            m.d.sync += [
                                self.va.eq(self.data[ 0: 8]),
                                self.vb.eq(self.data[ 8:16]),
                                self.vc.eq(self.data[16:24]),
                                self.vd.eq(self.data[24:32])
                            ]
                            m.next = 'V_1'
                        with m.Case(5): # b101, DECIMAL print + <SPACE>
                            m.d.sync += [
                                self.bcd1.mag.eq(9), # 1000000000
                                self.bcd1.i_val.eq(self.data)
                            ]
                            m.next = 'D_1'
                        with m.Case(6): # b110, HEX print 32 bit + <SPACE>
                            m.d.sync += [
                                self.h_1a.eq(self.data[24:32]), # high order byte
                                self.h_1b.eq(self.data[16:24]),
                                self.h_1c.eq(self.data[ 8:16]),
                                self.h_1d.eq(self.data[ 0: 8]),
                                self.h_spaceout.eq(0) # no spaces in between bytes
                            ]
                            m.next = 'H32_1a'
                        with m.Case(7): # b111, HEX print 32 bit as 4 times 8 bit with <SPACE> separators
                            m.d.sync += [
                                self.h_1a.eq(self.data[24:32]), # high order byte
                                self.h_1b.eq(self.data[16:24]),
                                self.h_1c.eq(self.data[ 8:16]),
                                self.h_1d.eq(self.data[ 0: 8]),
                                self.h_spaceout.eq(1) # DO put spaces in between bytes
                            ]
                            m.next = 'H32_1a'
            # VERBATIM (ascii printing)
            # LSB printed first, 0s are skipped
            with m.State('V_1'):
                with m.If(self.uartfifo.w_rdy):
                    with m.If( (self.va > 0)):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(self.va),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'V_2'
            with m.State('V_2'):
                with m.If(self.uartfifo.w_rdy):
                    with m.If( (self.vb > 0)):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(self.vb),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'V_3'
            with m.State('V_3'):
                with m.If(self.uartfifo.w_rdy):
                    with m.If( (self.vc > 0)):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(self.vc),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'V_4'
            with m.State('V_4'):
                with m.If(self.uartfifo.w_rdy):
                    with m.If( (self.vd > 0)):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(self.vd),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'READY'

            # DECIMAL + SPACE
            with m.State('D_1'):
                # o_j is highest digit
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(8),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_2'
            with m.State('D_2'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(7),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_3'
            with m.State('D_3'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(6),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_4'
            with m.State('D_4'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(5),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_5'
            with m.State('D_5'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(4),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_6'
            with m.State('D_6'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(3),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_7'
            with m.State('D_7'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(2),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_8'
            with m.State('D_8'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(1),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)
                        ]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_9'
            with m.State('D_9'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        self.bcd1.mag.eq(0),
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    m.next = 'D_10'
            with m.State('D_10'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.sync += [
                        ##### self.bcd1.mag.eq(0), # 10^0, 1..9
                        self.bcd1.i_val.eq(self.bcd1.o_rem)
                    ]
                    with m.If( (self.bcd1.o_digit > 0) | (self.nonlead0 == 1) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)
                        ]
                        m.d.sync += [
                            self.nonlead0.eq(1)
                        ]
                    # check for 0000 case, i.e. have not found a non zero digit, and o_a is
                    # 0 as well. Print 0
                    with m.If( (self.bcd1.o_digit == 0) | (self.nonlead0 == 0) ):
                        m.d.comb += [
                            self.uartfifo.w_data.eq(48 + self.bcd1.o_digit),
                            self.uartfifo.w_en.eq(1)
                        ]
                    m.next = 'SPACE'

            # HEX 32 bit + SPACE
            with m.State('H32_1a'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_1.o_upper),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'H32_1b'
            with m.State('H32_1b'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_1.o_lower),
                            self.uartfifo.w_en.eq(1)]
                    with m.If(self.h_spaceout):
                        m.next = 'H32_2a_space'
                    with m.Else():
                        m.next = 'H32_2a'

            with m.State('H32_2a_space'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                        # write gap
                        self.uartfifo.w_data.eq(32), # SPACE
                        self.uartfifo.w_en.eq(1)
                    ]
                    m.next = 'H32_2a'
            with m.State('H32_2a'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_2.o_upper),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'H32_2b'
            with m.State('H32_2b'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_2.o_lower),
                            self.uartfifo.w_en.eq(1)]
                    with m.If(self.h_spaceout):
                        m.next = 'H32_3a_space'
                    with m.Else():
                        m.next = 'H32_3a'

            with m.State('H32_3a_space'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                        # write gap
                        self.uartfifo.w_data.eq(32), # SPACE
                        self.uartfifo.w_en.eq(1)
                    ]
                    m.next = 'H32_3a'
            with m.State('H32_3a'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_3.o_upper),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'H32_3b'
            with m.State('H32_3b'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_3.o_lower),
                            self.uartfifo.w_en.eq(1)]
                    with m.If(self.h_spaceout):
                        m.next = 'H32_4a_space'
                    with m.Else():
                        m.next = 'H32_4a'

            with m.State('H32_4a_space'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                        # write gap
                        self.uartfifo.w_data.eq(32), # SPACE
                        self.uartfifo.w_en.eq(1)
                    ]
                    m.next = 'H32_4a'
            with m.State('H32_4a'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_4.o_upper),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'H32_4b'
            with m.State('H32_4b'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                            self.uartfifo.w_data.eq(self.h8d_4.o_lower),
                            self.uartfifo.w_en.eq(1)]
                    m.next = 'SPACE'

            with m.State('SPACE'):
                with m.If(self.uartfifo.w_rdy):
                    m.d.comb += [
                        # write gap
                        self.uartfifo.w_data.eq(32), # SPACE
                        self.uartfifo.w_en.eq(1)
                    ]
                    m.next = 'READY'
        return m

class Top(Elaboratable):
    def __init__(self, sim):
        self.b_fifo = SyncFIFOBuffered(width=8, depth=32) # UART
        self.printer = UART_Printer(self.b_fifo)

        # sim helper
        self.sim = sim

    def elaborate(self, platform):
        m = Module()
        m.domains.sync = ClockDomain()

        if not self.sim:
            clk12 = platform.request("clk12")
            m.d.comb += ClockSignal().eq(clk12.i)
        else:
            clk12 = None

        m.submodules.b_fifo = self.b_fifo
        m.submodules.printer = self.printer

        return m

def p():
    # depth >4 leads to use of memory (4k primitive, see build/top.rpt)
    top = Top(sim=False)
    platform = ICEBreakerPlatform()
    platform.build(top, do_program=True)

def g():
    top = Top(sim=False)
    platform = ICEBreakerPlatform()
    print(verilog.convert(top, ports=[], platform=platform))

def s():
    # Note: direct_mode true/false -> exact same vcd!
    top = Top(sim=True)
    platform = None
    fragment = Fragment.get(top, platform=platform)
    with open("top.vcd", "w") as vcd_file:
        with pysim.Simulator(fragment, vcd_file=vcd_file) as sim:
            sim.add_clock(83e-9)
            def driver_proc():
                # ---------
                # PROTOCOL: cmd are the high order bits
                #
                # DECIMAL (cmd=5)
                #
                p = Cat(Signal(maxn, reset=0x5F41112), Const(0x5)) # 99881234 = 0x5F41112
                print(p.shape())
                yield top.printer.din.eq(p)
                yield
                yield top.printer.we.eq(1)
                yield
                yield top.printer.we.eq(0)
                yield
                #
                p = Cat(Signal(maxn, reset=0x21FCCE715), Const(0x5)) #  9123456789 = 0x21FCCE715
                print(p.shape())
                yield top.printer.din.eq(p)
                yield
                yield top.printer.we.eq(1)
                yield
                yield top.printer.we.eq(0)
                yield
                #
                p = Cat(Signal(maxn, reset=0x2540BE3FF), Const(0x5)) #  9999999999 = 0x2540BE3FF
                print(p.shape())
                yield top.printer.din.eq(p)
                yield
                yield top.printer.we.eq(1)
                yield
                yield top.printer.we.eq(0)
                yield
                #
                #
                # VERBATIM (cmd=4)
                #
                # padding needed to get to 34 bits data
                # CR, LF, BELL, 0<ignored>, pad(2bit), cmd(3bit)
                p = Cat(Signal(8,reset=13), Signal(8,reset=10), Signal(8,reset=7), Signal(8), Signal(2), Const(4))
                #p = Cat(Signal(8,reset=13), Signal(8,reset=10), Signal(8,reset=7), Signal(8), Signal(2), Const(4))
                print(p.shape())
                yield top.printer.din.eq(p)
                yield
                yield top.printer.we.eq(1)
                yield
                yield top.printer.we.eq(0)
                yield
                #
                # padding needed to get to 34 bits data
                # R,E,T,O, pad(2bit), cmd(3bit)
                p = Cat(Signal(8,reset=ord('R')), Signal(8,reset=ord('E')), Signal(8,reset=ord('T')), Signal(8,reset=ord('O')), Signal(2), Const(4))
                #p = Cat(Signal(8,reset=13), Signal(8,reset=10), Signal(8,reset=7), Signal(8), Signal(2), Const(4))
                print(p.shape())
                yield top.printer.din.eq(p)
                yield
                yield top.printer.we.eq(1)
                yield
                yield top.printer.we.eq(0)
                yield

                #
                #
                #yield top.printer.din.eq(Cat(Const(9876543210), Const(0x5)))
                #yield top.printer.we.eq(1)
                #yield
                #yield top.printer.we.eq(0)

                # HEX TESTS
                # padding needed to get to 34 bits data
                # "AB" pad(2bit), cmd(3bit) = 6 Hex 8bit print
                print('HEX TESTS')
                p = Cat(Signal(8,reset=0), Signal(8,reset=0), Signal(8,reset=2), Signal(8,reset=1), Signal(2), Const(6))
                print(p.shape())
                yield top.printer.din.eq(p)
                yield
                yield top.printer.we.eq(1)
                yield
                yield top.printer.we.eq(0)
                yield


                print('done.')

            def rcv_proc():
                while (True):
                    while not (yield top.b_fifo.readable):
                        yield
                    v = yield from top.b_fifo.read()
                    print(v)

            sim.add_sync_process(driver_proc())
            sim.add_sync_process(rcv_proc())
            sim.run_until(10e-6, run_passive=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    p_action = parser.add_subparsers(dest="action")
    p_action.add_parser("simulate")
    p_action.add_parser("generate")
    p_action.add_parser("program")
    args = parser.parse_args()
    if args.action == "generate":
        g()
    elif args.action == "simulate":
        s()
    elif args.action == "program":
        p()

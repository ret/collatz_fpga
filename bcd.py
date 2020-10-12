#!/usr/local/bin/python3
from nmigen import *
from nmigen.cli import main
from nmigen.back import pysim, verilog

class CMAG(Elaboratable):
    def __init__(self):
        # i_mag goes from 0 to 9, corresponding to 1,10,100,...,1000000000
        self.i_mag = Signal(len(Const(9)))
        self.o1 = Signal(len(Const(9999999999))) # 34 bits
        self.o2 = Signal(len(Const(9999999999)))
        self.o3 = Signal(len(Const(9999999999)))
        self.o4 = Signal(len(Const(9999999999)))
        self.o5 = Signal(len(Const(9999999999)))
        self.o6 = Signal(len(Const(9999999999)))
        self.o7 = Signal(len(Const(9999999999)))
        self.o8 = Signal(len(Const(9999999999)))
        self.o9 = Signal(len(Const(9999999999)))

    def elaborate(self, platform):
        m = Module()
        with m.Switch(self.i_mag):
            with m.Case(0):
                m.d.comb += [
                    self.o1.eq(1), self.o2.eq(2),
                    self.o3.eq(3), self.o4.eq(4),
                    self.o5.eq(5), self.o6.eq(6),
                    self.o7.eq(7), self.o8.eq(8),
                    self.o9.eq(9)
                ]
            with m.Case(1):
                m.d.comb += [
                    self.o1.eq(10), self.o2.eq(20),
                    self.o3.eq(30), self.o4.eq(40),
                    self.o5.eq(50), self.o6.eq(60),
                    self.o7.eq(70), self.o8.eq(80),
                    self.o9.eq(90)
                ]
            with m.Case(2):
                m.d.comb += [
                    self.o1.eq(100), self.o2.eq(200),
                    self.o3.eq(300), self.o4.eq(400),
                    self.o5.eq(500), self.o6.eq(600),
                    self.o7.eq(700), self.o8.eq(800),
                    self.o9.eq(900)
                ]
            with m.Case(3):
                m.d.comb += [
                    self.o1.eq(1000), self.o2.eq(2000),
                    self.o3.eq(3000), self.o4.eq(4000),
                    self.o5.eq(5000), self.o6.eq(6000),
                    self.o7.eq(7000), self.o8.eq(8000),
                    self.o9.eq(9000)
                ]
            with m.Case(4):
                m.d.comb += [
                    self.o1.eq(10000), self.o2.eq(20000),
                    self.o3.eq(30000), self.o4.eq(40000),
                    self.o5.eq(50000), self.o6.eq(60000),
                    self.o7.eq(70000), self.o8.eq(80000),
                    self.o9.eq(90000)
                ]
            with m.Case(5):
                m.d.comb += [
                    self.o1.eq(100000), self.o2.eq(200000),
                    self.o3.eq(300000), self.o4.eq(400000),
                    self.o5.eq(500000), self.o6.eq(600000),
                    self.o7.eq(700000), self.o8.eq(800000),
                    self.o9.eq(900000)
                ]
            with m.Case(6):
                m.d.comb += [
                    self.o1.eq(1000000), self.o2.eq(2000000),
                    self.o3.eq(3000000), self.o4.eq(4000000),
                    self.o5.eq(5000000), self.o6.eq(6000000),
                    self.o7.eq(7000000), self.o8.eq(8000000),
                    self.o9.eq(9000000)
                ]
            with m.Case(7):
                m.d.comb += [
                    self.o1.eq(10000000), self.o2.eq(20000000),
                    self.o3.eq(30000000), self.o4.eq(40000000),
                    self.o5.eq(50000000), self.o6.eq(60000000),
                    self.o7.eq(70000000), self.o8.eq(80000000),
                    self.o9.eq(90000000)
                ]
            with m.Case(8):
                m.d.comb += [
                    self.o1.eq(100000000), self.o2.eq(200000000),
                    self.o3.eq(300000000), self.o4.eq(400000000),
                    self.o5.eq(500000000), self.o6.eq(600000000),
                    self.o7.eq(700000000), self.o8.eq(800000000),
                    self.o9.eq(900000000)
                ]
            with m.Case(9):
                m.d.comb += [
                    self.o1.eq(1000000000), self.o2.eq(2000000000),
                    self.o3.eq(3000000000), self.o4.eq(4000000000),
                    self.o5.eq(5000000000), self.o6.eq(6000000000),
                    self.o7.eq(7000000000), self.o8.eq(8000000000),
                    self.o9.eq(9000000000)
                ]
        return m

class BCD1_32(Elaboratable):
    def __init__(self):
        self.mag     = Signal(len(Const(1000000000)))
        self.i_val   = Signal(len(Const(9999999999)), reset=8192)
        self.o_digit = Signal(len(Const(9)))
        self.o_rem   = Signal(len(Const(9999999999)))
        # internal
        self.cmag    = CMAG()

    def elaborate(self, platform):
        m = Module()
        m.submodules.cmag = self.cmag
        m.d.comb += [
            self.cmag.i_mag.eq(self.mag)
        ]
        with m.If(  self.i_val.__ge__( self.cmag.o9) ):
            m.d.comb += [self.o_digit.eq(9), self.o_rem.eq( self.i_val - self.cmag.o9 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o8) ):
            m.d.comb += [self.o_digit.eq(8), self.o_rem.eq( self.i_val - self.cmag.o8 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o7) ):
            m.d.comb += [self.o_digit.eq(7), self.o_rem.eq( self.i_val - self.cmag.o7 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o6) ):
            m.d.comb += [self.o_digit.eq(6), self.o_rem.eq( self.i_val - self.cmag.o6 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o5) ):
            m.d.comb += [self.o_digit.eq(5), self.o_rem.eq( self.i_val - self.cmag.o5 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o4) ):
            m.d.comb += [self.o_digit.eq(4), self.o_rem.eq( self.i_val - self.cmag.o4 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o3) ):
            m.d.comb += [self.o_digit.eq(3), self.o_rem.eq( self.i_val - self.cmag.o3 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o2) ):
            m.d.comb += [self.o_digit.eq(2), self.o_rem.eq( self.i_val - self.cmag.o2 )]
        with m.Elif(self.i_val.__ge__( self.cmag.o1) ):
            m.d.comb += [self.o_digit.eq(1), self.o_rem.eq( self.i_val - self.cmag.o1 )]
        with m.Else():
            m.d.comb += [self.o_digit.eq(0), self.o_rem.eq( self.i_val                )]
        return m

if __name__ == "__main__":
    bcd = BCD1_32()
    print(verilog.convert(bcd, ports=[bcd.i_val, bcd.o_digit, bcd.o_rem]))
    with pysim.Simulator(bcd,
                         vcd_file=open("bcd.vcd", "w"),
                         gtkw_file=open("bcd.gtkw", "w"),
                         traces=[bcd.i_val, bcd.o_digit, bcd.o_rem]) as sim:
        sim.add_clock(20e-9)
        def bcd_proc():
            yield
            n = 9111222333
            nbits = len(Const(n))
            print(len(Const(n))) # 34 bits
            yield bcd.mag.eq(9) # 1000000000
            yield bcd.i_val.eq(Signal(nbits, reset=n))
            yield
            d=yield bcd.o_digit; r=yield bcd.o_rem
            print('%s %s' % (d,r))
            assert (d,r) == (9,111222333)
        sim.add_sync_process(bcd_proc())
        sim.run_until(1e-6, run_passive=True)
        print('passed.')

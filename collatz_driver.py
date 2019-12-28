from nmigen import *
from nmigen.cli import main
from nmigen_boards.icebreaker import ICEBreakerPlatform
from nmigen.back import pysim, verilog

from collatz import Collatz
from uart_fifo import UART_FIFO
from uart_printer import UART_Printer

import argparse

(maxn,_) = Signal(range(0, 9999999999)).shape() # single digit billions, needs 34 bits

class Top(Elaboratable):
    def __init__(self, sim, sim_tx_cycle_accurate, xwidth, nwidth):
        self.clk  = Signal()
        self.tx = Signal()
        self.rx = Signal()

        # self.mem = Memory(width=8, depth=16, init=[0xa, 0xb, 0xc])
        self.mem = Memory(width=8, depth=16, init=[ord(c) for c in 'Hello World!'])
        self.x = Signal(xwidth)
        self.xwidth = xwidth
        self.nwidth = nwidth

        # sim helper
        self.sim = sim
        self.sim_tx_cycle_accurate = sim_tx_cycle_accurate

        self.xmax = Signal(xwidth)
        self.nmax = Signal(nwidth)
        self.nmaxcnt = Signal(nwidth)

    def elaborate(self, platform):
        m = Module()
        m.domains.sync = ClockDomain()

        if not self.sim:
            clk12 = platform.request("clk12")
            m.d.comb += ClockSignal().eq(clk12.i)
            board_uart = platform.request("uart")
        else:
            clk12 = None
            board_uart = None

        self.uartfifo = uartfifo = UART_FIFO(sim=self.sim,
                                             sim_tx_cycle_accurate=self.sim_tx_cycle_accurate,
                                             width=8,
                                             depth=1024,
                                             clk=clk12,
                                             board_uart=board_uart)
        self.collatz = collatz = Collatz(xwidth, nwidth)
        self.uart_printer = uart_printer = UART_Printer(uartfifo.w_fifo)
        m.submodules.uartfifo = uartfifo
        m.submodules.collatz = collatz
        m.submodules.uart_printer = uart_printer

        m.d.comb += [
            self.tx.eq(uartfifo.tx),
            self.rx.eq(uartfifo.rx)
        ]

        m.d.comb += [
            self.collatz.ld_x.eq(self.x),
        ]
        with m.FSM(reset='AWAIT_START') as fsm:
            with m.State('AWAIT_START'):
                with m.If(uartfifo.r_fifo.r_rdy):
                    with m.If(uartfifo.r_fifo.r_data == 65):
                        # A is the start character
                        m.d.comb += [
                            uartfifo.r_fifo.r_en.eq(1),
                        ]
                        m.next = 'INC'
                    with m.Else():
                        # swallow and ignore
                        m.d.comb += [
                            uartfifo.r_fifo.r_en.eq(1)
                        ]
                        m.next = 'AWAIT_START'
            with m.State('INC'):
                m.d.sync += [
                    self.x.eq(self.x + 1)
                ]
                m.next = 'CALC_START'
            with m.State('CALC_START'):
                m.d.comb += [
                    self.collatz.start.eq(1)
                ]
                m.next = 'CALC'
            with m.State('CALC'):
                with m.If(self.collatz.done):
                    with m.If(self.collatz.out > self.nmax):
                        m.d.sync += [
                            self.nmax.eq(self.collatz.out),
                            self.nmaxcnt.eq(self.nmaxcnt+1),
                            self.xmax.eq(self.x),
                        ]
                        # was a new record, print to terminal
                        m.next = 'R_1'
                    with m.Elif(self.collatz.err_n):
                        m.next = 'ERR_N_1'
                    with m.Elif(self.collatz.err_x):
                        m.next = 'ERR_X_1'
                    with m.Else():
                        # not a new record sequence length, and neither an error
                        m.next = 'INC'

            with m.State('R_1'):
                with m.If(uart_printer.writable):
                    m.d.comb += [
                        uart_printer.din.eq( Cat(self.nmaxcnt, Signal(34-nwidth), Const(0x5)) ),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'N_1'

            with m.State('N_1'):
                with m.If(uart_printer.writable):
                    m.d.comb += [
                        uart_printer.din.eq( Cat(self.nmax, Signal(34-nwidth), Const(0x5)) ),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'X_1'

            with m.State('X_1'):
                with m.If(uart_printer.writable):
                    m.d.comb += [
                        uart_printer.din.eq( Cat(self.xmax, Const(0x5)) ),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'END'
            #        m.next = 'SUFFIX_1'

            #with m.State('SUFFIX_1'):
            #    with m.If(uart_printer.writable):
            #        m.d.comb += [
            #            uart_printer.din.eq( Cat(Signal(32, reset=0x123456AB), Signal(2), Const(0x7)) ),
            #            uart_printer.we.eq(1)
            #        ]
            #        m.next = 'END'

            with m.State('ERR_N_1'):
                with m.If(uart_printer.writable):
                    # padding needed to get to 34 bits data
                    # CR, LF, BELL, 0<ignored>, pad(2bit), cmd(3bit)
                    p = Cat(Signal(8,reset=ord('N')), Signal(8,reset=ord(' ')), Signal(8), Signal(8), Signal(2), Const(4))
                    m.d.comb += [
                        uart_printer.din.eq(p),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'ERR_N_2'
            with m.State('ERR_N_2'):
                with m.If(uart_printer.writable):
                    m.d.comb += [
                        uart_printer.din.eq( Cat(self.collatz.out, Signal(34-nwidth), Const(0x5)) ),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'ERR_N_3'
            with m.State('ERR_N_3'):
                with m.If(uart_printer.writable):
                    m.d.comb += [
                        uart_printer.din.eq( Cat(self.x, Const(0x5)) ),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'END'

            with m.State('ERR_X_1'):
                with m.If(uart_printer.writable):
                    # padding needed to get to 34 bits data
                    # CR, LF, BELL, 0<ignored>, pad(2bit), cmd(3bit)
                    p = Cat(Signal(8,reset=ord('X')), Signal(8,reset=ord(' ')), Signal(8), Signal(8), Signal(2), Const(4))
                    m.d.comb += [
                        uart_printer.din.eq(p),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'ERR_X_2'
            with m.State('ERR_X_2'):
                with m.If(uart_printer.writable):
                    m.d.comb += [
                        uart_printer.din.eq( Cat(self.collatz.out, Signal(34-nwidth), Const(0x5)) ),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'ERR_X_3'
            with m.State('ERR_X_3'):
                with m.If(uart_printer.writable):
                    m.d.comb += [
                        uart_printer.din.eq( Cat(self.x, Const(0x5)) ),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'END'

            with m.State('END'):
                with m.If(uart_printer.writable):
                    # padding needed to get to 34 bits data
                    # CR, LF, BELL, 0<ignored>, pad(2bit), cmd(3bit)
                    p = Cat(Signal(8,reset=13), Signal(8,reset=10), Signal(8,reset=7), Signal(8), Signal(2), Const(4))
                    m.d.comb += [
                        uart_printer.din.eq(p),
                        uart_printer.we.eq(1)
                    ]
                    m.next = 'INC'
        return m

xwidth = 34 # to represent max decimal 9'999'999'999 (single digit trillion)
nwidth = 12 # max sequence length = 2048

def p():
    # depth >4 leads to use of memory (4k primitive, see build/top.rpt)
    top = Top(sim=False, sim_tx_cycle_accurate=False, xwidth=xwidth, nwidth=nwidth)
    platform = ICEBreakerPlatform()
    platform.build(top, do_program=True)

def g():
    top = Top(sim=False, sim_tx_cycle_accurate=False, xwidth=xwidth, nwidth=nwidth)
    platform = ICEBreakerPlatform()
    print(verilog.convert(top, ports=[top.tx, top.rx], platform=platform))

def s(tx_cycle_accurate=False):
    top = Top(sim=True, sim_tx_cycle_accurate=tx_cycle_accurate, xwidth=xwidth, nwidth=nwidth)
    # in simulation we set the platform to None
    platform = None # ICEBreakerPlatform()
    fragment = Fragment.get(top, platform=platform)
    with open("top.vcd", "w") as vcd_file:
        with pysim.Simulator(fragment, vcd_file=vcd_file) as sim:
            sim.add_clock(83e-9)
            def driver_proc():
                # ---------
                yield top.uartfifo.uart.rx_data.eq(65)
                yield top.uartfifo.uart.rx_rdy.eq(1)
                yield
                yield top.uartfifo.uart.rx_rdy.eq(0)
            sim.add_sync_process(driver_proc())
            sim.run_until(100*1e-6, run_passive=True)
            # sim.run_until(30*1000*1e-6, run_passive=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    p_action = parser.add_subparsers(dest="action")
    p_action.add_parser("simulate")
    p_action.add_parser("timing")
    p_action.add_parser("generate")
    p_action.add_parser("program")
    args = parser.parse_args()
    if args.action == "generate":
        g()
    elif args.action == "simulate":
        s(tx_cycle_accurate=False)
    elif args.action == "timing":
        s(tx_cycle_accurate=True)
    elif args.action == "program":
        p()

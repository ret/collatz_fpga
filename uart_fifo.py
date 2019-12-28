from nmigen import *
from nmigen.back import pysim, verilog
from nmigen.cli import main
from nmigen.lib.fifo import *
from nmigen_boards.icebreaker import ICEBreakerPlatform

from uart_wrapper_nmigen import UART
from uart_wrapper_sim import UART_SIM

class UART_FIFO(Elaboratable):
    def __init__(self, sim, sim_tx_cycle_accurate, width, depth, clk, board_uart):
        self.sim = sim
        self.sim_tx_cycle_accurate = sim_tx_cycle_accurate

        self.tx = Signal() # output from uart_fifo to host, fed by t_fifo
        self.tx_active = Signal() # high while busy transmitting data
        self.tx_done = Signal() # high for one cycle, after tx completed
        self.rx = Signal() # input to uart_fifo from host, feeds r_fifo

        # data coming into the fifo_uart from the host
        #   -- TODO use r_port record in the future
        self.r_fifo_readable = Signal()
        self.r_fifo_re = Signal()
        self.r_fifo_dout = Signal(width)

        # data leaving the fifo_uart to the host
        #   -- TODO use w_port record in the future
        self.w_fifo_writable = Signal()
        self.w_fifo_we = Signal()
        self.w_fifo_din = Signal(width)

        # internal
        if not self.sim:
            self.uart = UART(clk, board_uart)
        else:
            self.uart = UART_SIM()

        self.r_fifo = SyncFIFOBuffered(width=width, depth=depth)
        self.w_fifo = SyncFIFOBuffered(width=width, depth=depth)

    def elaborate(self, platform):
        m = Module()
        # FIXME rm if
        if self.uart:
            m.submodules.uart = self.uart
        m.submodules.r_fifo = self.r_fifo
        m.submodules.w_fifo = self.w_fifo
        # FIXME rm if
        if self.uart:
            m.d.comb += [
                self.tx.eq(self.uart.tx),
                self.rx.eq(self.uart.rx)
            ]
        m.d.comb += [
            # r_fifo, rd port
            self.r_fifo_readable.eq(self.r_fifo.readable),
            self.r_fifo_re.eq(self.r_fifo.re),
            self.r_fifo_dout.eq(self.r_fifo.dout),
            # w_fifo, wr port
            self.w_fifo_writable.eq(self.w_fifo.writable),
            self.w_fifo_we.eq(self.w_fifo.we),
            self.w_fifo_din.eq(self.w_fifo.din)
        ]
        # host to device loop
        with m.FSM(reset='AWAIT_UART_DATA') as fsm_rd_from_host:
            with m.State('AWAIT_UART_DATA'):
                # TODO send backpresure to host if r_fifo is close to full:
                # [Use the fifo's .level signal to gauge 'close to full'
                # and pause the sender ahead of the overrun!]
                # Use SW flow control (send XOFF/XON)
                # See https://pyserial.readthedocs.io/en/latest/pyserial_api.html
                # and https://en.wikipedia.org/wiki/Software_flow_control
                with m.If(self.uart.rx_rdy & self.r_fifo.writable):
                    m.d.comb += [
                        self.r_fifo.din.eq(self.uart.rx_data),
                        self.r_fifo.we.eq(1)
                    ]
                    m.next = 'AWAIT_UART_DATA' # LOOP
        # device to host loop
        with m.FSM(reset='AWAIT_FIFO_DATA') as fsm_wr_to_host:
            with m.State('AWAIT_FIFO_DATA'):
                # checks to see if uart is ready to transmit data
                with m.If(self.w_fifo.readable & ~self.uart.tx_active):
                    m.d.comb += [
                        self.uart.tx_data.eq(self.w_fifo.dout),
                        self.uart.tx_rdy.eq(1),
                    ]
                    # not needed in sim since we're reading from
                    # the w_fifo ourselves in the uart.py driver_proc.
                    if platform:
                        m.d.comb += [
                            # rd fifo (dequeue element)
                            self.w_fifo.re.eq(1)
                        ]
                    if self.sim_tx_cycle_accurate:
                        m.d.comb += [
                            # rd fifo (dequeue element)
                            self.w_fifo.re.eq(1)
                        ]
                    m.next = 'AWAIT_FIFO_DATA_COMPLETE'
            with m.State('AWAIT_FIFO_DATA_COMPLETE'):
                # wait until uart is done transmitting data
                with m.If(self.uart.tx_done):
                    m.next = 'AWAIT_FIFO_DATA'
        return m

#
#                +--------------------+
#                |       (rd port)    |                     w_fifo_writable
#                |     fsm_wr_to_host |    user (wr port)   w_fifo_we
#                |           |        |    |                w_fifo_din
#     (host) tx <- uart(tx) <------ w_fifo <- device
#     (host) rx -> uart(rx) ------> r_fifo -> device
#                |           |        |    |                r_fifo_readable
#                |   fsm_rd_from_host |    user (rd port)   r_fifo_re
#                |           |        |                     r_fifo_dout
#                |       (wr port)    |
#                +--------------------+
#

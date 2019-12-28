from nmigen import *

from uart_nmigen import UART_NMIGEN

class UART(Elaboratable):
    def __init__(self, clk12, board_uart):
        self.clk     = clk12
        self.board_uart = board_uart

        self.tx      = Signal()
        self.tx_data = Signal(8)
        self.tx_rdy   = Signal() # was nandland tx_dv
        self.tx_active = Signal()
        self.tx_done = Signal() # high for one cycle, after tx completed (strobes)

        self.rx      = Signal()
        self.rx_data = Signal(8)
        self.rx_rdy   = Signal() # strobe

        self.rx_rdy_old   = Signal()
        self.tx_ack_old = Signal()

    def elaborate(self, platform):
        m = Module()

        # uart_nmigen = UART_NMIGEN(104) # 12MHz / 115200 baud = 104
        # uart_nmigen = UART_NMIGEN(26) # 12MHz / 460800 baud = 26
        # uart_nmigen = UART_NMIGEN(10) # 12MHz / 1228800 baud = 10 (9.7), ~122kB/s [8+start+stop bits)
        uart_nmigen = UART_NMIGEN(4) # 12MHz / 3000000 baud = 4, ~300kB/s [8+start+stop bits)
        m.d.sync += [
            self.tx_ack_old.eq(uart_nmigen.tx_ack),
            self.rx_rdy_old.eq(uart_nmigen.rx_rdy)
        ]
        m.d.comb += [
            # TX
            self.tx.eq(uart_nmigen.tx_o),
            uart_nmigen.tx_data.eq(self.tx_data),
            uart_nmigen.tx_rdy.eq(self.tx_rdy),
            self.tx_active.eq(~uart_nmigen.tx_ack),
            self.tx_done.eq(~self.tx_ack_old & uart_nmigen.tx_ack), # strobe
            # RX
            uart_nmigen.rx_i.eq(self.rx),
            self.rx_data.eq(uart_nmigen.rx_data),
            self.rx_rdy.eq(~self.rx_rdy_old & uart_nmigen.rx_rdy), # strobe
            # set to 1 permanently, if not set to 1, ovf will rise after the
            # first byte is received.
            uart_nmigen.rx_ack.eq(1)
        ]
        m.submodules.uart_nmigen = uart_nmigen
        m.d.comb += [
            self.board_uart.tx.o.eq(self.tx), # x
            # in this order of assignment, I get the dreaded error:
            #     File "/Users/reto/Library/Python/3.7/lib/python/site-packages/ ...
            #          ... nmigen/hdl/ir.py", line 379, in add_defs
            #       assert defs[sig] is self
            #     AssertionError
            # -> ERRORS: self.board_uart.rx.i.eq(self.rx)
            # but flippin the order of the terms, works:
            self.rx.eq(self.board_uart.rx.i)
        ]
        return m

        # works on OSX Catalina with FTDI driver from https://www.ftdichip.com/Drivers/VCP.htm
        #   https://www.ftdichip.com/Support/Documents/DataSheets/ICs/DS_FT2232D.pdf
        #   $ python uart_mem.py program
        #   $ miniterm.py - 3000000 (use the last, i.e. 5: /dev/cu.usbserial-ib3P7AOGB 'iCEBreaker V1.0d - iCEBreaker V1.0d'
        #   before programming with iceprog
        #     $ sudo kextunload -b com.FTDI.driver.FTDIUSBSerialDriver
        #   then to use the miniterm
        #     $ sudo kextload -b com.FTDI.driver.FTDIUSBSerialDriver

from nmigen import *

class Counter(Elaboratable):
    def __init__(self, rr):
        ndigits,_ = rr.shape()
        self.rr = rr
        self.start = Signal()
        self.inc = Signal()
        self.v = Signal(ndigits)
        self.o = Signal()
        self.done = Signal()

    def elaborate(self, platform):
        m = Module()
        with m.If(self.start):
          m.d.sync += self.v.eq(0)
        with m.Else():
            with m.If(self.v == self.rr):
                m.d.comb += [
                    self.o.eq(1),
                    self.done.eq(1)
                ]
                m.d.sync += [
                    self.v.eq(0)
                ]
            with m.Else():
                m.d.sync += self.v.eq(self.v + 1)
        return m

class UART_SIM(Elaboratable):
    def __init__(self):
        self.tx        = Signal()
        self.tx_active = Signal()
        self.tx_done   = Signal()
        self.tx_data   = Signal(8)
        self.tx_rdy    = Signal() # was nandland tx_dv

        self.rx        = Signal()
        self.rx_data   = Signal(8)
        self.rx_rdy    = Signal() # was nandland rx_dv

        # FIXME: make 104 configurable
        self.cnt       = Counter(Const(104)) # floor(12MHz / 115200) = 104

    def elaborate(self, platform):
        m = Module()
        m.submodules.cnt = self.cnt
        # simulate tx somewhat realistically in term of
        # active and done signals, which are needed
        # for proper flow control with sending
        # elements.
        # Note: to precisely mimic NANDLANDs uart_tx, we
        # lower tx_active and only then stobe tx_done.
        #
        # after tx_rdy, assert active for N cycles, and
        # strobe done for 1 cycle thereafter.
        #
        with m.FSM(reset='TX_AWAIT_START') as fsm:
            with m.State('TX_AWAIT_START'):
                with m.If(self.tx_rdy):
                    m.d.comb += [
                        self.cnt.start.eq(1)
                    ]
                    m.d.sync += [
                        self.tx_active.eq(1)  # assert tx_active
                    ]
                    m.next = 'TX_SEND_ACTIVE'
            with m.State('TX_SEND_ACTIVE'):
                with m.If(~self.cnt.done):
                    m.d.comb += [
                        self.cnt.inc.eq(1),
                    ]
                    m.next = 'TX_SEND_ACTIVE'
                with m.Else():
                    m.d.sync += [
                        self.tx_active.eq(0)
                    ]
                    m.next = 'TX_DONE'
            with m.State('TX_DONE'):
                m.d.comb += [
                    self.tx_done.eq(1) # strobe
                ]
                m.next = 'TX_AWAIT_START'
        return m

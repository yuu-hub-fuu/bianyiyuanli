from nexa.backend.regalloc import Interval, linear_scan
from nexa.runtime.rt_core import rt_chan_new, rt_chan_recv, rt_chan_send


def test_linear_scan_with_spill():
    intervals = [Interval('a', 0, 10), Interval('b', 1, 9), Interval('c', 2, 8)]
    alloc = linear_scan(intervals, ['r1', 'r2'])
    assert sum(v is None for v in alloc.values()) >= 1


def test_channel_send_recv():
    ch = rt_chan_new(1)
    rt_chan_send(ch, 42)
    assert rt_chan_recv(ch) == 42

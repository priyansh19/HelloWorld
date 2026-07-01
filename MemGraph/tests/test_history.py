from memgraph.history import History


def test_append_and_values_order_oldest_to_newest():
    h = History(5)
    for v in (1, 2, 3):
        h.append(v)
    assert h.values() == [1.0, 2.0, 3.0]


def test_ring_discards_oldest_beyond_capacity():
    h = History(3)
    h.extend([1, 2, 3, 4, 5])
    assert h.values() == [3.0, 4.0, 5.0]
    assert len(h) == 3


def test_latest_peak_average():
    h = History(10)
    h.extend([10, 20, 30])
    assert h.latest() == 30
    assert h.peak() == 30
    assert h.average() == 20


def test_empty_accessors_use_defaults():
    h = History(4)
    assert h.latest(default=-1) == -1
    assert h.peak(default=-1) == -1
    assert h.average(default=-1) == -1
    assert h.values() == []


def test_resize_keeps_newest_when_shrinking():
    h = History(5)
    h.extend([1, 2, 3, 4, 5])
    h.resize(2)
    assert h.values() == [4.0, 5.0]
    assert h.maxlen == 2


def test_resize_grow_preserves_all():
    h = History(2)
    h.extend([1, 2])
    h.resize(5)
    h.extend([3, 4])
    assert h.values() == [1.0, 2.0, 3.0, 4.0]


def test_minimum_capacity_enforced():
    h = History(1)
    assert h.maxlen == 2


def test_clear():
    h = History(3)
    h.extend([1, 2])
    h.clear()
    assert h.values() == []

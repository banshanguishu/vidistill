from vidistill.jobs import JobStore


def test_store_init_creates_schema():
    store = JobStore(":memory:")
    # Querying the table should not raise
    cur = store._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    assert cur.fetchone() is not None

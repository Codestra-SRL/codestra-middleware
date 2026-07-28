"""Real PostgreSQL concurrency proof for inclusive campaign ranges."""
import asyncio
import os
import uuid
import asyncpg


INSERT = """
INSERT INTO campaign_extension_allocation
(id,campaign_id,campaign_number,allocation_public_id,extension_start,
 extension_end,created_by,policy_hash,source_change_id)
VALUES($1,$2,$3,$4,$5,$6,'concurrency-test',$7,'test')
"""


async def insert(pool, name, number, start, end, delay=0):
    async with pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute(
                INSERT, uuid.uuid4(), name, number, "ALLOC-" + name,
                start, end, "c" * 64,
            )
            await asyncio.sleep(delay)
            await transaction.commit()
            return "PASS"
        except asyncpg.ExclusionViolationError:
            await transaction.rollback()
            return "OVERLAP"


async def main():
    pool = await asyncpg.create_pool(os.environ["TEST_DATABASE_URL"])
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE campaign_extension_allocation")
    exact = await asyncio.gather(
        insert(pool, "EXACT1", 100, 7100, 7199, .1),
        insert(pool, "EXACT2", 200, 7100, 7199),
    )
    assert sorted(exact) == ["OVERLAP", "PASS"]
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE campaign_extension_allocation")
    partial = await asyncio.gather(
        insert(pool, "PART1", 100, 7100, 7199, .1),
        insert(pool, "PART2", 200, 7199, 7298),
    )
    assert sorted(partial) == ["OVERLAP", "PASS"]
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE campaign_extension_allocation")
    contained = await asyncio.gather(
        insert(pool, "OUTER", 100, 7100, 7199, .1),
        insert(pool, "INNER", 200, 7120, 7130),
    )
    assert sorted(contained) == ["OVERLAP", "PASS"]
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE campaign_extension_allocation")
    adjacent = await asyncio.gather(
        insert(pool, "ADJ1", 100, 7100, 7199, .1),
        insert(pool, "ADJ2", 200, 7200, 7299),
    )
    assert adjacent == ["PASS", "PASS"]
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE campaign_extension_allocation")
    many = await asyncio.gather(*[
        insert(pool, "BLOCK%d" % number, number, 7000 + number, 7099 + number)
        for number in (100, 200, 300, 400, 500)
    ])
    assert many == ["PASS"] * 5
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE campaign_extension_allocation")
        transaction = connection.transaction()
        await transaction.start()
        await connection.execute(
            INSERT, uuid.uuid4(), "ROLLBACK", 100, "ALLOC-ROLLBACK",
            7100, 7199, "c" * 64,
        )
        await transaction.rollback()
    assert await insert(pool, "AFTERROLLBACK", 200, 7100, 7199) == "PASS"
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE campaign_extension_allocation"
            " SET allocation_status='RETIRED' WHERE campaign_id='AFTERROLLBACK'"
        )
    assert await insert(pool, "REUSE", 300, 7100, 7199) == "OVERLAP"
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM campaign_extension_allocation"
        ) == 1
    await pool.close()
    print("CONCURRENT_OVERLAP_GATE=PASS")
    print("CONCURRENT_ADJACENT_GATE=PASS")
    print("RACE_CONDITION_GATE=PASS")
    print("TRANSACTION_ROLLBACK_GATE=PASS")
    print("RETIRED_RANGE_NON_REUSE_GATE=PASS")


if __name__ == "__main__":
    asyncio.run(main())

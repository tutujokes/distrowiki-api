import asyncio
from api.services.scrapling_distrowatch_service import ScraplingDistroWatchClient

async def main():
    client = ScraplingDistroWatchClient()
    res = await client.fetch_distro_details("ubuntu")
    print(res)

if __name__ == "__main__":
    asyncio.run(main())

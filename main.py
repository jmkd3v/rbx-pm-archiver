from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

from dateutil.parser import parse
from timeit import default_timer as timer
import aiofiles
import aiohttp
import asyncio
import typer
import json

app = typer.Typer()
cutoff_date = datetime(2019, 1, 1, tzinfo=timezone.utc)


class OutputFormat(Enum):
    json = "json"
    # csv = "csv"
    # html = "html"


async def get_authenticated_user(
        session: aiohttp.ClientSession
):
    async with session.request(
        method="GET",
        url="https://users.roblox.com/v1/users/authenticated"
    ) as response:
        return await response.json()


async def get_raw_messages(
        session: aiohttp.ClientSession,
        page_number: int,
        page_size: int,
        message_tab: str
):
    async with session.request(
        method="GET",
        url="https://privatemessages.roblox.com/v1/messages",
        params={
            "pageNumber": page_number,
            "pageSize": page_size,
            "messageTab": message_tab
        }
    ) as response:
        return await response.json()


async def get_valid_messages(
        session: aiohttp.ClientSession,
        rest_delay: int = 1
):
    messages = []

    page_size = 20

    page_count = -1
    message_count = -1

    async def filter_messages(page_number):
        nonlocal page_count, message_count

        raw_messages = await get_raw_messages(
            session=session,
            page_number=page_number,
            page_size=page_size,
            message_tab="Inbox"
        )

        for raw_message in raw_messages["collection"]:
            created_date = parse(raw_message["created"])
            if created_date > cutoff_date:
                continue
            if not raw_message["isSystemMessage"]:
                continue
            messages.append(raw_message)

        page_count = raw_messages["totalPages"]
        message_count = raw_messages["totalCollectionSize"]

    await filter_messages(0)  # this fills in the data
    typer.echo(f"Filtering {message_count} messages in {page_count} pages")

    chunk_size = 32  # send this many requests in parallel

    for page_offset in range(1, page_count, chunk_size):
        tasks = []
        for page_number in range(page_offset, min(page_offset + chunk_size, page_count)):
            tasks.append(filter_messages(page_number))
        await asyncio.gather(*tasks)
        await asyncio.sleep(rest_delay)

    typer.echo(f"Found {len(messages)} valid messages")

    return messages


async def main(
        path: Path,
        output_format: OutputFormat,
        token: str,
        rest_delay: int
):
    async with aiohttp.ClientSession(
        cookies={
            ".ROBLOSECURITY": token
        },
        raise_for_status=True
    ) as session:
        user = await get_authenticated_user(session)
        user_id = user["id"]
        user_name = user["name"]
        user_display_name = user["displayName"]

        if user_name == user_display_name:
            name_string = user_name
        else:
            name_string = f"{user_display_name} (@{user_name})"

        typer.echo(f"Logged in as {name_string} - https://www.roblox.com/users/{user_id}/profile")
        start_time = timer()
        messages = await get_valid_messages(session)
        if output_format == OutputFormat.json:
            async with aiofiles.open(
                file=path,
                mode="w",
                encoding="utf-8"
            ) as file:
                await file.write(json.dumps(messages, indent=2))
        # elif output_format == OutputFormat.csv:
        #     pass
        end_time = timer()
        typer.echo(f"Awesome! Done in {end_time-start_time:.04f} seconds.")


@app.command()
def root(
        path: Path = typer.Option(
            default=...,
            help="The file to dump messages to. Must not exist.",
            resolve_path=True
        ),
        output_format: OutputFormat = typer.Option(
            default="json",
            help="The output format to use. If set to HTML, path must be a directory. If not, path must be a file."
        ),
        token: str = typer.Option(
            default=...,
            help="A .ROBLOSECURITY token."
        ),
        rest_delay: int = typer.Option(
            default=1,
            help="How long to wait between requests. Increase this if you encounter 429 errors."
        )
):
    """
    if output_format == OutputFormat.html:
        assert path.is_dir() and path.exists(), "outputting to HTML requires a directory"
    """

    asyncio.get_event_loop().run_until_complete(main(
        path=path,
        output_format=output_format,
        token=token,
        rest_delay=rest_delay
    ))


if __name__ == '__main__':
    app()
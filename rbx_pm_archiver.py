from typing import Set, List

from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

from dateutil.parser import parse
from timeit import default_timer as timer

import aiofiles
import aiohttp
import asyncio
import shutil

import typer
import json

root_path = Path(__file__).parent
html_assets_path = root_path / "html_assets"

template_loader = FileSystemLoader(searchpath=html_assets_path)
template_environment = Environment(loader=template_loader, enable_async=True)

index_template = template_environment.get_template("index.html")
message_template = template_environment.get_template("message.html")

app = typer.Typer()
cutoff_date = datetime(2019, 1, 1, tzinfo=timezone.utc)


class OutputFormat(Enum):
    json = "json"
    # csv = "csv"
    html = "html"


async def get_authenticated_user(
        session: aiohttp.ClientSession
):
    async with session.request(
            method="GET",
            url="https://users.roblox.com/v1/users/authenticated"
    ) as response:
        return await response.json()


def chunks(lst, n):
    """Yield successive n-sized chunks from lst. https://stackoverflow.com/a/312464"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def get_headshots(
        session: aiohttp.ClientSession,
        user_ids: List[int],
        size: str = "48x48"
):
    user_ids = list(set(user_ids))
    headshots = {}
    for user_id_chunk in chunks(user_ids, 100):
        async with session.request(
                method="GET",
                url="https://thumbnails.roblox.com/v1/users/avatar-headshot",
                params={
                    "userIds": user_id_chunk,
                    "size": size,
                    "format": "Png",
                    "isCircular": "false"
                }
        ) as response:
            data = (await response.json())["data"]
            for item in data:
                headshots[item["targetId"]] = item["imageUrl"]
    return headshots


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
        rest_delay: int = 1,
        convert_dates: bool = False
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
            if convert_dates:
                raw_message["created"] = created_date
            if created_date > cutoff_date:
                continue
            from_roblox = raw_message["sender"]["id"] == 1
            if not from_roblox:
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
    if convert_dates:
        messages.sort(key=lambda message: message["created"], reverse=True)

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
        archive_date = datetime.now(timezone.utc)

        if output_format == OutputFormat.json:
            messages = await get_valid_messages(session, convert_dates=False)

            async with aiofiles.open(
                file=path,
                mode="w",
                encoding="utf-8"
            ) as file:
                await file.write(json.dumps(messages, indent=2))
        elif output_format == OutputFormat.html:
            messages = await get_valid_messages(session, convert_dates=True)

            # start by moving over static files (should be async but whatever)
            for a_path in {
                html_assets_path / "style.css",
                html_assets_path / "favicon.ico",
                html_assets_path / "favicon.svg"
            }:
                b_path = path / a_path.name
                shutil.copy(a_path, b_path)

            print("Getting headshots...")
            user_headshots = await get_headshots(
                session=session,
                user_ids=[message["sender"]["id"] for message in messages]
            )

            async with aiofiles.open(
                file=path / "index.html",
                mode="w",
                encoding="utf-8"
            ) as index_file:
                await index_file.write(await index_template.render_async(
                    messages=[
                        {
                            "path": f"{message['id']}.html",
                            "title": message["subject"],
                            "author": {
                                "thumbnail_url": user_headshots[message["sender"]["id"]],
                                "profile_url": f"https://www.roblox.com/users/{message['sender']['id']}/profile",
                                "name": message["sender"]["name"],
                                "display_name": message["sender"]["displayName"]
                            }
                        } for message in messages
                    ],
                    archive_date=archive_date.strftime("%m/%d/%Y, %H:%M:%S %Z")
                ))

            for message in messages:
                message_id = message["id"]
                message_path = path / f"{message_id}.html"
                author_id = message["sender"]["id"]

                async with aiofiles.open(
                    file=message_path,
                    mode="w",
                    encoding="utf-8"
                ) as message_file:
                    await message_file.write(await message_template.render_async(
                        message={
                            "title": message["subject"],
                            "body": message["body"],
                            "post_date": message["created"].strftime("%m/%d/%Y, %H:%M:%S %Z"),
                            "author": {
                                "thumbnail_url": user_headshots[author_id],
                                "profile_url": f"https://www.roblox.com/users/{author_id}/profile",
                                "name": message["sender"]["name"],
                                "display_name": message["sender"]["displayName"]
                            }
                        }
                    ))

        end_time = timer()
        typer.echo(f"Awesome! Done in {end_time - start_time:.04f} seconds.")


@app.command()
def root(
        path: Path = typer.Option(
            default=...,
            help="The file to dump messages to. If format is 'html', path must be a directory. If not, path must be a "
                 "non-existant file.",
            resolve_path=True
        ),
        output_format: OutputFormat = typer.Option(
            default="json",
            help="The output format to use."
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
    if output_format == OutputFormat.html:
        assert path.is_dir() and path.exists(), "outputting to HTML requires a directory"

    asyncio.get_event_loop().run_until_complete(main(
        path=path,
        output_format=output_format,
        token=token,
        rest_delay=rest_delay
    ))


if __name__ == '__main__':
    app()

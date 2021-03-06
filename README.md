# rbx-pm-archiver
On April 20th, 2022, Roblox is deleting all __system messages__ (not from other users) sent to users before January 1st, 2019.
This tool serves as a way to easily back up those messages for safe-keeping.

## Setup
1. Install Python 3.7 or later: https://www.python.org/downloads/
2. Install `typer`, `aiohttp`, `aiofiles`, `python-dateutil` and `jinja2`: `pip3 install typer aiohttp aiofiles python-dateutil jinja2`
3. Clone this repository to your computer and open it in your terminal

## Usage
For CLI usage, run `py rbx_pm_archiver.py --help`.
To obtain a token, find the `.ROBLOSECURITY` cookie from your browser and copy its contents.
Make sure you wrap it in double quotes before passing it as an argument - for example, don't do `--token _|WARNING|_abc`, do `--token "_|WARNING|_abc"`.

### JSON archives
rbx-pm-archiver can generate a JSON archive of your old messages. This won't be very human-readable, but it contains the most information, like author IDs, creation dates, updated dates, and more. It is recommended that you archive with this method at least once just so you have the JSON data for safe-keeping.
```
py rbx_pm_archiver.py --token ROBLOSECURITY_HERE --path messages.json
```

### HTML archives
rbx-pm-archiver can generate a rich, browsable HTML archive of your old messages. This is the easiest way to browse your old messages and is very human readable. If you use this method, you should also make a JSON archive as well as it contains more data.
![A screenshot of an archived message](/assets/demo_image.png)
Make sure you create the target folder (in this case, `./output`) before running this command!
```
py rbx_pm_archiver.py --token ROBLOSECURITY_HERE --path ./output --output-format html
```

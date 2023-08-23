import asyncio
import aiohttp
from datetime import datetime, timezone
from dateutil.parser import parse
from collections import defaultdict
import requests
import argparse

from rich.console import Console
from rich.table import Table

from wallet import *

TX_MIN = 10
TX_MIDDLE = 25
TX_MAX = 100
RATIO = 5
ETH_INDEX = 1
USDC_INDEX = 2
FEE_INDEX = 11

EMPTYCONTRACT = "0x01176a1bd84444c89232ec27754698e5d2e7e1a7f1539f12027f28b23ec9f3d8".lower()

base_columns = ["#", "eth", "usdc", "usdt", "dai", "tx", "最后交易", "day", "week", "mon", "金额", "fee"]

CONTRACTZKSTASK = (
    # ["0x03a20d4f7b4229e7c4863dab158b4d076d7f454b893d90a62011882dc4caca2a", "dmail"],
    ["0x04d0390b777b424e43839cd1e744799f3de6c176c7e32c1812a41dbd9c19db6a", "jiedi"],
    ["0x045e7131d776dddc137e30bdd490b431c7144677e97bf9369f629ed8d3fb7dd6", "jiedi"],        
    ["0x07e2a13b40fc1119ec55e0bcf9428eedaa581ab3c924561ad4e955f95da63138", "jiedi"],    
    ["0x010884171baf1914edc28d7afb619b40a4051cfae78a094a55d230f19e944a28", "ymswap"],    
    ["0x04270219d365d6b017231b52e92b3fb5d7c8378b05e9abc97724537a80e93b0f", "avnu"],
    ["0x04c0a5193d58f74fbace4b74dcf65481e734ed1714121bdc571da345540efa05", "zklend"],
    ["0x05900cfa2b50d53b097cb305d54e249e31f24f881885aae5639b0cd6af4ed298", "10kswap"],
    ["0x000023c72abdf49dffc85ae3ede714f2168ad384cc67d08524732acea90df325", "10kswap"],
    ["0x017e9e62c04b50800d7c59454754fe31a2193c9c3c6c92c093f2ab0faadf8c87", "10kswap"],
    ["0x030615bec9c1506bfac97d9dbd3c546307987d467a7f95d5533c2e861eb81f3f", "sithswap"],    
    ["0x05e86d570376e8dc917d241288150a3286c8ad7151638c152d787eca2b96aec3", "sithswap"],    
    ["0x02aab581754064a87ade1b680fd9756dc3a17440a87aaf496dcfb39fd163d1dd", "sithswap"],   
)

CONTRACT2TASK = {x.lower(): y for x, y in CONTRACTZKSTASK}

def get_task_colums():
    task_colums = []
    seen = set()

    for _, y in CONTRACTZKSTASK:
        if y not in seen:
            seen.add(y)
            task_colums.append(y)
    return task_colums

task_colums = get_task_colums()

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')
    
def get_eth_price():
    url = "https://www.okx.com/api/v5/market/ticker?instId=ETH-USD-SWAP"

    try:
        data = requests.get(url).json()
        price = data["data"][0]["last"]

        return float(price)
    except Exception as e:
        print(e)
        return 1935.0
ETHPRICE = get_eth_price()    
    
async def get_stark_activity(session, address):
    url = f"https://voyager.online/api/txns?to={address}&ps=50&p=1&type=null"

    days, weeks, months = set(), set(), set()
    fees = 0.
    tx = 0 

    async with session.get(url) as res:
        data = await res.json()    

        diff = datetime.now() - datetime.fromtimestamp((data["items"][0]["timestamp"]))

        pages = int(data["lastPage"])
        page = 1

    while page <= pages:
        url = f"https://voyager.online/api/txns?to={address}&ps=50&p={page}&type=null"
        page += 1
        async with session.get(url) as res:
            data = await res.json()    

            for item in data["items"]:
                if item["type"] == "INVOKE":
                    tx += 1

                dt = datetime.fromtimestamp(item["timestamp"])
                fees += int(item["actual_fee"]) / 1e18

                months.add(dt.strftime("%Y-%m"))
                weeks.add(dt.strftime("%Y-%W"))
                days.add(dt.strftime("%Y-%m-%d"))          

    diff_days = diff.days
    diff_hours = diff.seconds // 3600
    diff_mins = diff.seconds // 60
    if diff_days > 14:
        last_tx = f"[red]{diff_days}d[/red]"
    elif diff_days > 0:
        last_tx = f"{diff_days}d"
    elif diff_hours > 0:
        last_tx = f"{diff_hours}h"
    elif diff_mins > 0:
        last_tx = f"{diff_mins}m"   
    else:  
        last_tx = f"{diff.seconds}s"  

    mon = len(months)
    if mon < 2:
        mon = f"[red]{mon}[/red]"
    elif mon >= 9:
        mon = f"[bold][green]{mon}[/green][/bold]"        
    elif mon >= 6:
        mon = f"[green]{mon}[/green]"          

    if tx < TX_MIN:
        tx = f"[red]{tx}[/red]"
    elif tx >= TX_MAX:
        tx = f"[bold][green]{tx}[/green][/bold]"
    elif tx >= TX_MIDDLE:
        tx = f"[green]{tx}[/green]"

    return len(days), len(weeks), mon, round(fees, RATIO), last_tx, tx

async def get_stark_anount_and_contracts(session, address):
    url = f"https://voyager.online/api/contract/{address}/transfers?ps=50&p=1"
    async with session.get(url) as res:
        data = await res.json()    
        pages = int(data["lastPage"])
        page = 1    

    total_amounts = 0.
    seen = set()
    contracts = defaultdict(int)

    while page <= pages:
        url = f"https://voyager.online/api/contract/{address}/transfers?ps=50&p={page}"
        page += 1
        async with session.get(url) as res:
            data = await res.json()      

        for item in data["items"]:
            to_contract = item['transfer_to'].lower()
            if to_contract in CONTRACT2TASK:
                contracts[CONTRACT2TASK[to_contract]] += 1          

            # from_contract = item['transfer_from'].lower()
            # if from_contract in CONTRACT2TASK:
            #     contracts[CONTRACT2TASK[from_contract]] += 1                 

            if item['transfer_from'].lower() == address.lower() and to_contract != EMPTYCONTRACT and item["tx_hash"] not in seen:
                seen.add(item["tx_hash"])
                if item["token_symbol"] == "ETH":
                    total_amounts += float(item["transfer_value"]) * ETHPRICE
                elif item["token_symbol"] == "USDC":
                    total_amounts += float(item["transfer_value"])

    total_amounts = round(total_amounts, 2)
    if total_amounts < 10000:
        total_amounts = f"[red]{total_amounts}[/red]"
    elif total_amounts >= 250000:
        total_amounts = f"[bold][green]{total_amounts}[/green][/bold]"        
    elif total_amounts >= 50000:
        total_amounts = f"[green]{total_amounts}[/green]"                        

    contracts = [contracts[task] if task in contracts else 0 for task in task_colums]    

    return total_amounts, contracts             

async def get_stark_balances(session, address):
    url = f"https://voyager.online/api/contract/{address}/balances"

    try:
        async with session.get(url) as res:
            data = await res.json()        

            eth = round(float(data["ethereum"]["amount"]), RATIO) if "ethereum" in data else 0.
            usdc = round(float(data["usd-coin"]["amount"]), RATIO) if "usd-coin" in data else 0.
            usdt = round(float(data["tether"]["amount"]), RATIO) if "tether" in data else 0.
            dai = round(float(data["dai"]["amount"]), RATIO) if "dai" in data else 0.
    except Exception as e:
        return 0., 0., 0., 0.

    return eth, usdc, usdt, dai

async def get_all_starknet_info(session, address, wtype, idx):
    days, weeks, months, fees, last_tx, tx = await get_stark_activity(session, address)
    total_amounts, contracts = await get_stark_anount_and_contracts(session, address)
    eth, usdc, usdt, dai = await get_stark_balances(session, address)

    return [f"{wtype}-{idx+1}", eth, usdc, usdt, dai, tx, last_tx, days, weeks, months, total_amounts, fees] + contracts

async def rich_show(args):
    index = args.idx

    table = Table(title=f"Starknet: {str(datetime.now())[:19]}")
    for col in base_columns+task_colums:
        table.add_column(col)

    async with aiohttp.ClientSession() as session:
        if index == 0:
            tasks = []

            for idx, address in enumerate(ARGGENTLIST):
                tasks.append(asyncio.create_task(get_all_starknet_info(session, address, "Argent", idx)))

            for idx, address in enumerate(BRAAVOSLIST):
                tasks.append(asyncio.create_task(get_all_starknet_info(session, address, "Braavos", idx)))

            results = await asyncio.gather(*tasks)
            await session.close()

            eth = usdc = fee = 0
            for result in results:
                eth += result[ETH_INDEX]
                usdc += result[USDC_INDEX]
                fee += result[FEE_INDEX]

                if result[ETH_INDEX] <= 0.01:
                    result[ETH_INDEX] = f"[red]{result[ETH_INDEX]}[/red]"

                table.add_row(*[str(r) for r in result])

            last_row = ["" for _ in range(len(base_columns+task_colums))]
            last_row[0] = "总计"

            last_row[ETH_INDEX] = f"{round(eth, RATIO)}"
            last_row[USDC_INDEX] = f"{round(usdc, RATIO)}"
            last_row[FEE_INDEX] = f"{round(fee, RATIO)}"
            table.add_row(*last_row)

        else:
            idx = index-1
            wtype = args.wtype

            wallet_list = ARGGENTLIST if wtype == "Argent" else BRAAVOSLIST
            assert idx < len(wallet_list)

            address = wallet_list[idx]
            tasks = [asyncio.create_task(get_all_starknet_info(session, address, wtype, idx))]
            results = await asyncio.gather(*tasks)
            await session.close()    

            for result in results:
                
                if result[ETH_INDEX] <= 0.005:
                    result[ETH_INDEX] = f"[red]{result[ETH_INDEX]}[/red]"

                table.add_row(*[str(r) for r in result])

    Console().print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-idx', type=int, default=0)
    parser.add_argument('-wtype', type=str, default="Argent", choices=["Argent", "Braavos"])


    args = parser.parse_args()

    asyncio.run(rich_show(args))

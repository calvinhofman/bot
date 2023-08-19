import aiohttp
import asyncio
import datetime
from collections import defaultdict
from datetime import datetime
from statistics import median
from collections import Counter
from datetime import datetime, timedelta
import time
import requests
from collections import Counter
from statistics import mean
from itertools import islice
from walletdatacache import WalletDataCache
import json
import os

def read_config():
    config_path = 'config.json'
    default_data = {
        "telegram_bot_token": "",
        "additionalText": "",
        "admin_ids": [],
        "LOGGERBOT_TOKEN": "",
        "LOGGERBOT_GROUP_ID": "",
        "etherscan_api_key": ""
    }

    # If config file doesn't exist, create one with default values
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump(default_data, f)
        print("Config file created. Please provide the necessary values in config.json.")
        return default_data

    # If config file exists, read and return its content
    with open(config_path, 'r') as f:
        data = json.load(f)

    # Ensure all keys from default_data exist in the current config data
    for key, value in default_data.items():
        data.setdefault(key, value)  # This will add the key if it doesn't exist, with the default value

    # Save the potentially updated config data back to the file
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=4)

    return data

# Fetch the configuration
config = read_config()


ETHER_VALUE = 10**18
ETHERSCAN_API_URL = "https://api.etherscan.io/api"
ETHERSCAN_API_KEY = config.get("etherscan_api_key")
wallet_data_cache = WalletDataCache()

def get_eth_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
    response = requests.get(url)
    data = response.json()
    return data['ethereum']['usd']

async def fetch_transactions(session, address, action):
    params = {
        "module": "account",
        "action": action,
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "page": 1,  # start from first page
        "offset": 10000,  # transactions per page (max limit)
        "apikey": ETHERSCAN_API_KEY  # replace with your Etherscan API key
    }

    transactions = []
    while True:
        #print(f"Fetching {action} page {params['page']} for address {address}")
        async with session.get(ETHERSCAN_API_URL, params=params) as response:
            data = await response.json()
        transactions.extend(data['result'])
        #print(f"Fetched {len(data['result'])} transactions. Total transactions fetched: {len(transactions)}")
        # If less than the offset transactions are returned, we've fetched all transactions
        if len(data['result']) < params['offset']:
            break
        params['page'] += 1  # go to next page

    return transactions


    



def assign_transaction_type(token_dict2):
    """
    This function assigns transaction type to each token in the given dictionary, calculates several metrics, 
    and separates tokens based on their transactions. 

    Parameters:
        token_dict2 (dict): A dictionary where each key is a token name and its value is a list of transactions.

    Returns:
        updated_dict (dict): A dictionary where each key is a token name and its value is a dictionary containing:
                             - The token contract address
                             - A list of buy and sell transactions
                             - The number of buys and sells
                             - The first and last transaction time
                             - The total amount of ETH spent and gained
                             - The total gas spent on buy and sell transactions
                             - The profit and loss without and with gas considered
                             - The average percentage of tokens sold per sell
                             - The hash number of the first buy and last sell transaction
                             - The percentage of tokens sold and held
                             This dictionary only includes tokens that have either buy transactions only or both buy and sell transactions.
                             
        skipped_tokens (dict): A dictionary where each key is a token name and its value is a list of transactions.
                               This dictionary only includes tokens that have sell transactions only.

    The function processes each token's transactions, checking whether ETH was involved in the transaction, and whether the transaction 
    was a buy or a sell. Tokens that only involved sell transactions are put into the skipped_tokens dictionary and are excluded from the 
    updated_dict. Tokens with only buy transactions are kept in the updated_dict, but their sell-related metrics are not calculated or set. 
    For tokens with both buy and sell transactions, additional metrics are calculated, including the average percentage of tokens sold per sell, 
    and the percentage of tokens sold and held. 
    """
     
    updated_dict = {}
    skipped_tokens = {}
    all_gas_total = 0

    for token_name in token_dict2:
        eth_involved = True  
        for hash, transactions in token_dict2[token_name].items():
            transaction = transactions[0]
            if transaction["gainToken"] != 'ETH' and transaction["swappedToken"] != 'ETH':  
                eth_involved = False
                break
            if transaction['swapped']['contractAddress'].lower() in ['usdt', 'usdc']:  
                eth_involved = False
                break

        if not eth_involved:
            skipped_tokens[token_name] = token_dict2[token_name]
            continue  

        total_tokens_bought = 0
        total_tokens_sold = 0
        total_eth_spent = 0
        total_eth_gained = 0
        total_sell_gas = 0
        total_buy_gas = 0
        buy_gas_values = []
        sell_gas_values = []

        updated_dict[token_name] = {
            "contractaddress": "",
            "Buys": [],
            "Sells": [],
            "noOfBuys": 0,
            "noOfSells": 0,
            "firstTxTime": float("inf"),
            "lastTxTime": float("-inf"),
            "firstBuyHashNumber": "",
            "lastSellHashNumber": "",
        }

        for hash, transactions in token_dict2[token_name].items():
            if not isinstance(transactions, list):
                print(f"Unexpected data type for transactions: {type(transactions)}, with hash: {hash}")
                continue

            transaction = transactions[0]

            if "swappedToken" in transaction:
                swap = {
                    "transactionType": "",
                    "swappedToken": transaction["swappedToken"],
                    "swappedTokenAdd": transaction['swapped']['contractAddress'],
                    "swap amount": transaction["swap amount"],
                    "swapWithDeci": transaction["swapWithDeci"],
                    "gainToken": transaction["gainToken"],
                    "gain amount": transaction["gain amount"],
                    "gainWithDeci": transaction["gainWithDeci"],
                    "timeStamp": transaction["timeStamp"],
                    "hash": hash,
                    "taxed": transaction["taxed"],
                    "gasFee": transaction['gasfee']
                }

                if transaction["gainToken"] == 'ETH':
                    swap['transactionType'] = 'Sell'
                    total_tokens_sold += transaction["swapWithDeci"]
                    total_eth_gained += transaction["gainWithDeci"]
                    total_sell_gas += transaction['gasfee']
                    sell_gas_values.append(transaction['gasfee'])
                    updated_dict[token_name]["Sells"].append(swap)
                    updated_dict[token_name]["noOfSells"] += 1
                else:
                    swap['transactionType'] = 'Buy'
                    total_tokens_bought += transaction["gainWithDeci"]
                    total_eth_spent += transaction["swapWithDeci"]
                    total_buy_gas += transaction['gasfee']
                    buy_gas_values.append(transaction['gasfee'])
                    updated_dict[token_name]["Buys"].append(swap)
                    updated_dict[token_name]["noOfBuys"] += 1

                updated_dict[token_name]["contractaddress"] = transaction['swappedTokenAddress']
                updated_dict[token_name]["firstTxTime"] = min(updated_dict[token_name]["firstTxTime"], int(transaction["timeStamp"]))
                updated_dict[token_name]["lastTxTime"] = max(updated_dict[token_name]["lastTxTime"], int(transaction["timeStamp"]))

        updated_dict[token_name]["totalEthSpent"] = total_eth_spent
        updated_dict[token_name]["totalEthGained"] = total_eth_gained
        updated_dict[token_name]["buyGasTotal"] = total_buy_gas
        updated_dict[token_name]["sellGasTotal"] = total_sell_gas
        updated_dict[token_name]["TotalGasTotal"] = total_sell_gas + total_buy_gas
        updated_dict[token_name]["profitLossWithoutGas"] = total_eth_gained - total_eth_spent
        updated_dict[token_name]["profitInXWithoutGas"] = total_eth_gained / total_eth_spent if total_eth_spent != 0 else 0
        updated_dict[token_name]["profitLossIncludingGas"] = total_eth_gained - total_eth_spent - total_buy_gas - total_sell_gas
        updated_dict[token_name]["profitInXIncludingGas"] = (total_eth_gained - total_buy_gas - total_sell_gas) / total_eth_spent if total_eth_spent != 0 else 0
        updated_dict[token_name]["firstTxTime"] = datetime.fromtimestamp(updated_dict[token_name]["firstTxTime"]).strftime('%Y-%m-%d %H:%M:%S')
        updated_dict[token_name]["lastTxTime"] = datetime.fromtimestamp(updated_dict[token_name]["lastTxTime"]).strftime('%Y-%m-%d %H:%M:%S')

         # After processing all transactions for a token, check if it has only sells and no buys
        if len(updated_dict[token_name]["Buys"]) == 0 and len(updated_dict[token_name]["Sells"]) > 0:
            # If the token has only sells, move it to the skipped tokens dictionary
            skipped_tokens[token_name] = updated_dict.pop(token_name)
        else:
            # If the token has buys (either only buys or both buys and sells), continue processing it
            if len(updated_dict[token_name]["Buys"]) > 0 and len(updated_dict[token_name]["Sells"]) > 0:
                sell_percentages = []
                for sell in updated_dict[token_name]["Sells"]:
                    sell_percentages.append(sell["swapWithDeci"] / total_tokens_bought * 100 if total_tokens_bought != 0 else 0)
                updated_dict[token_name]["averagePercentOfTokensSoldPerSell"] = sum(sell_percentages) / len(sell_percentages) if sell_percentages else 0
                updated_dict[token_name]["percentageTokensSold"] = (total_tokens_sold / total_tokens_bought) * 100 if total_tokens_bought != 0 else 0
                updated_dict[token_name]["percentageTokensHeld"] = ((total_tokens_bought - total_tokens_sold) / total_tokens_bought) * 100 if total_tokens_bought != 0 else 0
                updated_dict[token_name]["firstBuyHashNumber"] = updated_dict[token_name]["Buys"][0]['hash']
                updated_dict[token_name]["lastSellHashNumber"] = updated_dict[token_name]["Sells"][-1]['hash']

                if updated_dict[token_name]["percentageTokensHeld"] < 0:
                    skipped_tokens[token_name] = updated_dict.pop(token_name)

    return updated_dict, skipped_tokens











async def get_token_swaps(address):
    async with aiohttp.ClientSession() as session:
        txlist_dict = {}
        txlistinternal_dict = {}
        liquidity_swap = {}

        wallet_data = await wallet_data_cache.update_data_if_needed(session, address)

        tx_normal = wallet_data['tx_normal']
        tx_token = wallet_data['tx_token']
        tx_internal = wallet_data['tx_internal']


        # Build dictionaries for quick access
        for item in tx_normal:
            txlist_dict[item['hash']] = item

        for item in tx_internal:
            txlistinternal_dict[item['hash']] = item

        # Go through all token transactions and group up matching hashes
        #print("Searching for matching token hashes...")
        token_dict = {}
        for item in tx_token:
            token_dict.setdefault(item['hash'], []).append(item)
        #print("Matching token hashes finished..")

        # if there is more than one tokenTx in the hash from token_dict that means one of those
        # tx's will be the token used to swap and the other will be what token they swapped for
        # if the tx is from the wallet, it is the token that was used for the swap
        # put all tokens inside token_dict2
        #print('Searching for token to token swaps...')
        token_dict2 = {}
        unrecognisedTx = []
        errorTx = []

        for i in token_dict:
            if len(token_dict[i]) > 1:  # if there are more than one token swap for a single hash

                fromwalletTx = None
                towalletTx = None
                otherTx = None
                gainedToken = None
                burnTx = None
                taxedSwap = None
                taxedTx = None

                for tkn in token_dict[i]:  # loop through all token tx for the same hash and find which are from address and to address etc
                    if tkn['from'] == address:

                        if tkn['to'] == tkn['contractAddress']:
                            otherTx = tkn
                            continue
                        if tkn['to'] == '0x0000000000000000000000000000000000000000':
                            #print("burn or something")
                            burnTx = tkn
                            continue
                            print("dfdsf")

                        fromwalletTx = tkn

                    if tkn['to'] == address:
                        towalletTx = tkn

                if towalletTx == None:  # if we dont have a towallettx value it's probably an eth value, look through internal to find it
                    if token_dict[i][0]['hash'] in txlistinternal_dict:
                        towalletTx = txlistinternal_dict[token_dict[i][0]['hash']]
                        gainedToken = "ETH"

                if fromwalletTx == None:
                    unrecognisedTx.append(token_dict[i])
                    continue
                if towalletTx == None:
                    unrecognisedTx.append(token_dict[i])
                    continue

                swapped = fromwalletTx
                swappedAmount = fromwalletTx['value']
                gained = towalletTx
                swappedToken = fromwalletTx['tokenName']
                swappedTokenAddress = fromwalletTx['contractAddress']

                #get gas cost for tx
                gas_price_wei = int(swapped['gasPrice']) # Gas price in wei
                gas_used = int(swapped['gasUsed']) # Amount of gas used
                gas_cost_wei = gas_price_wei * gas_used  # Total cost in wei
                gas_cost_eth = gas_cost_wei / 1e18

                if gainedToken == None:  # I can't remember why we do this maybe something to do with internal tx
                    gainedToken = towalletTx['tokenName']

                gainedAmount = towalletTx["value"]
                timestamp = towalletTx["timeStamp"]
                hash = towalletTx['hash']

                if otherTx != None:  # if we have a value in other tx it is most likely tax
                    taxedSwap = otherTx['value']
                    taxedTx = otherTx

                if swappedToken == "ETH":
                    if swappedAmount != None:
                        if float(swappedAmount) < 0.01:
                            continue
                    else:
                        continue
                if gainedToken == "ETH":
                    if gainedAmount != None:
                        if float(gainedAmount) < 0.01:
                            continue
                    else:
                        continue

                if swappedToken == "ETH" and gainedToken == "ETH":
                    continue

                if gainedToken == 'Wrapped Ether':
                    gainedToken = 'ETH'
                    
                if swappedToken == 'Wrapped Ether':
                    swappedToken = 'ETH'
                    
                

                try:
                    if gainedToken == "ETH":
                        gainedDeci = float(gainedAmount) / ETHER_VALUE
                    else:
                        gainedDeci = float(gainedAmount) / 10 ** int(gained['tokenDecimal'])

                    if swappedToken == "ETH":
                        swappedDeci = float(swappedAmount) / ETHER_VALUE
                    else:
                        swappedDeci = float(swappedAmount) / 10 ** int(swapped['tokenDecimal'])
                except Exception as e:
                    print(e)

                swap = {
                    "swapped": swapped,
                    "swappedToken": swappedToken,
                    "swappedTokenAddress": swappedTokenAddress,
                    "swap amount": swappedAmount,
                    "swapWithDeci": swappedDeci,
                    "gained": gained,
                    "gainToken": gainedToken,
                    "gainWithDeci": gainedDeci,
                    "gain amount": gainedAmount,
                    "timeStamp": timestamp,
                    "hash": hash,
                    "taxed": taxedSwap,
                    "taxedTx": taxedTx,
                    "gasfee":gas_cost_eth,
                }

                if swap['swappedToken'] == "Uniswap V2" or swap['gainToken'] == "Uniswap V2":
                    continue

                if gainedToken == 'ETH':
                    if swappedToken in token_dict2.keys():
                        if hash in token_dict2[swappedToken].keys():
                            token_dict2[swappedToken][hash].append(swap)
                        else:
                            token_dict2[swappedToken][hash] = [swap]
                    else:
                        token_dict2[swappedToken] = {hash: [swap]}
                else:
                    if gainedToken in token_dict2.keys():
                        if hash in token_dict2[gainedToken].keys():
                            token_dict2[gainedToken][hash].append(swap)
                        else:
                            token_dict2[gainedToken][hash] = [swap]
                    else:
                        token_dict2[gainedToken] = {hash: [swap]}

        #print("Token to token swaps finished..")

        # Handle normal ETH to token or token to ETH swaps
        #print("Handling normal ETH to token or token to ETH swaps...")
        for i in token_dict:
            if len(token_dict[i]) == 1:
                fromwalletTx = None
                towalletTx = None
                otherTx = None
                gainedToken = None
                burnTx = None
                taxedSwap = None
                taxedTx = None
                swappedAmount = None
                gainedAmount = None
                gained = None
                swapped = None

                errorTx = []

                if token_dict[i][0]['from'] == address:  # normal token swap to ETH
                    swapped = token_dict[i][0]
                    gained = None
                if token_dict[i][0]['to'] == address:  # normal token swap for ETH
                    swapped = None
                    gained = token_dict[i][0]

                timestamp = token_dict[i][0]['timeStamp']
                hash = token_dict[i][0]['hash']


                if gained != None:  # if we gained tokens, it would have been for ETH (ETH for token)(Continuation of previous response)
                    gainedToken = gained['tokenName']
                    gainedAmount = gained['value']
                    swappedToken = 'ETH'
                    if hash in txlist_dict:
                        swappedAmount = txlist_dict[hash]['value']
                        swapped = txlist_dict[hash]

                else:  # if we didn't gain tokens, we would have gained ETH (token for ETH)
                    gainedToken = 'ETH'
                    if not swapped: #if for whatever reason we have 0 gains and 0 eth, skip
                        continue
                    else:
                        swappedToken = swapped['tokenName']
                    swappedAmount = swapped['value']
                    if hash in txlistinternal_dict:
                        gainedAmount = txlistinternal_dict[hash]['value']
                        gained = txlistinternal_dict[hash]

                if swappedToken == "ETH":
                    if swappedAmount != None:
                        if float(swappedAmount) < 0.01:
                            continue
                    else:
                        continue
                if gainedToken == "ETH":
                    if gainedAmount != None:
                        if float(gainedAmount) < 0.01:
                            continue
                    else:
                        continue

                if swappedToken == "ETH" and gainedToken == "ETH":
                    continue

                if gainedToken == '':
                    print("token error")
                    errorTx.append(tkn)
                    continue

                if gainedToken == "ETH":
                    gainedDeci = float(gainedAmount) / ETHER_VALUE
                else:
                    gainedDeci = float(gainedAmount) / 10 ** int(gained['tokenDecimal'])

                if swappedToken == "ETH":
                    swappedDeci = float(swappedAmount) / ETHER_VALUE
                else:
                    swappedDeci = float(swappedAmount) / 10 ** int(swapped['tokenDecimal'])

                
                #get gas cost for tx
                gas_price_wei = int(swapped['gasPrice']) # Gas price in wei
                gas_used = int(swapped['gasUsed']) # Amount of gas used
                gas_cost_wei = gas_price_wei * gas_used  # Total cost in wei
                gas_cost_eth = gas_cost_wei / 1e18

                swappedTokenAddress = swapped['contractAddress']
                if swappedTokenAddress == '':
                    swappedTokenAddress = gained['contractAddress']


                swap = {
                    "swapped": swapped,
                    "swappedToken": swappedToken,
                    "swappedTokenAddress": swappedTokenAddress,
                    "swap amount": swappedAmount,
                    "swapWithDeci": swappedDeci,
                    "gained": gained,
                    "gainToken": gainedToken,
                    "gainWithDeci": gainedDeci,
                    "gain amount": gainedAmount,
                    "timeStamp": timestamp,
                    "hash": hash,
                    "taxed": taxedSwap,
                    "taxedTx": taxedTx,
                    "gasfee":gas_cost_eth,
                }


               

                if swap['swappedToken'] == "Uniswap V2" or swap['gainToken'] == "Uniswap V2":
                    continue

                if gainedToken == 'ETH':
                    if swappedToken in token_dict2.keys():
                        if hash in token_dict2[swappedToken].keys():
                            token_dict2[swappedToken][hash].append(swap)
                        else:
                            token_dict2[swappedToken][hash] = [swap]
                    else:
                        token_dict2[swappedToken] = {hash: [swap]}
                else:
                    if gainedToken in token_dict2.keys():
                        if hash in token_dict2[gainedToken].keys():
                            token_dict2[gainedToken][hash].append(swap)
                        else:
                            token_dict2[gainedToken][hash] = [swap]
                    else:
                        token_dict2[gainedToken] = {hash: [swap]}

        #print("Handling normal ETH to token or token to ETH swaps...")

        tokk = {}
  
        # Build dictionaries for quick access
        for token_name in token_dict2:
            for hash in token_dict2[token_name]:
                tokk[hash] = token_name

  
        # with the hashes from tokk (created from token_dict2) txlist and txlistinternal, compare the values and pair any matches
        #this just adds any missing normal/internal tx's
        for hash, nam in tokk.items():
            if hash in txlist_dict:
                thingToAdd = txlist_dict[hash]
                token_dict2[nam][hash].append(thingToAdd)
                #print("added normalTx to tokenlist")
            if hash in txlistinternal_dict:
                thingToAdd = txlistinternal_dict[hash]
                token_dict2[nam][hash].append(thingToAdd)

       
        

        #print("Finished getting and adding tokens")

        return token_dict2
    




async def return_wallet_summary(address):
    ethprice = get_eth_price()
    swaps = await get_token_swaps(address)
    swaps,skipped = assign_transaction_type(swaps)
    sortbyx,sortbyprofit,sorttotaltx = sort_updated_dict(swaps)
    pf = address_analysis_v2(swaps)

    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    #fetch the first entry of each sorted list
    first_by_x = sortbyx[next(iter(sortbyx))]
    first_by_profit = sortbyprofit[next(iter(sortbyprofit))]
    first_by_tx = sorttotaltx[next(iter(sorttotaltx))]

    telegram_string = f"""
<b>💼 Wallet Summary:</b>
{address}

📅 Active Day: <code>{days_of_week[pf['most_active_day_of_week']]}</code>

<b>🔵 Tokens:</b>
🎲 Purchased: <code>{pf['tokens_bought']}</code> 
🟢 Profitable: <code>{pf['profitable_tokens']} ({pf['profitable_tokens_percentage']:.2f}%)</code>
🔴 Unprofitable: <code>{pf['tokens_bought'] - pf['profitable_tokens']} ({pf['unprofitable_token_percentage']:.2f}%)</code>

<b>🔄 Transactions:</b>
➡️ ETH Spent: <code>{pf['total_eth_spent_including_buy_gas']:.4f} ETH</code>
┗ <code>${pf['total_eth_spent_including_buy_gas']*ethprice:,.2f}</code>
⬅️ ETH Gained: <code>{pf['total_eth_gained_including_sell_gas']:.4f} ETH</code>
┗ <code>${pf['total_eth_gained_including_sell_gas']*ethprice:,.2f}</code>

<b>📊 Averages:</b>
💸 Spend/Token: <code>{pf['average_eth_spent_per_token_including_buyfee']:.4f} ETH</code>
┗ <code>${pf['average_eth_spent_per_token_including_buyfee']*ethprice:,.2f}</code>
💰 Gain/Token: <code>{pf['average_eth_gained_per_token_including_sellfee']:.4f} ETH</code>
┗ <code>${pf['average_eth_gained_per_token_including_sellfee']*ethprice:,.2f}</code>
🚀 Avg. X's: <code>{pf['average_xs']:.2f}</code>
⛽ Gas/Token: <code>{pf['average_gas_spent_per_token']:.4f} ETH</code>
┗ <code>${pf['average_gas_spent_per_token']*ethprice:,.2f}</code>
📉 Avg. % of Bag Sold: <code>{pf['averagePercentOfTokensSoldPerSell']:.2f}%</code>

<b>⚖️ Profits:</b>
📈 Rating: <code>{pf['profit_rating_including_gas']:.2f}%</code>
📊 Net: <code>{pf['net_profit_percentage']:.2f}%</code>
💡 Success Ratio: <code>{pf['profitable_investment_ratio']:.2f}%</code>

<b>🏦 Profit/Loss:</b>
🔷 ETH: <code>{pf['total_eth_profit_loss']:.4f}</code>
┗ $<code>{pf['total_eth_profit_loss']*ethprice:,.2f}</code>
💹 ROI: <code>{pf['total_roi']:.2f}%</code>

<b>🎖️ Most X's:</b> 
<b>{next(iter(sortbyx))}</b> 
<a href="https://etherscan.io/address/{first_by_x['contractaddress']}"><i>{first_by_x['contractaddress']}</i></a>
🟢 Buys: <code>{first_by_x['noOfBuys']}</code> 
🔴 Sells: <code>{first_by_x['noOfSells']}</code>
➡️ Eth Spent<code>: {first_by_x['totalEthSpent'] + first_by_x['buyGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(first_by_x['totalEthSpent'] + first_by_x['buyGasTotal']):,.2f}</code>
💰 Eth Gained<code>: {first_by_x['totalEthGained'] - first_by_x['sellGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(first_by_x['totalEthGained'] - first_by_x['sellGasTotal']):,.2f}</code>
🚀 X's: <code>{first_by_x['profitInXIncludingGas']:.2f}X</code> 
🔴 Tokens Sold: <code>{first_by_x.get('percentageTokensSold', 0.00):.2f}%</code>
💎 Tokens Left: <code>{first_by_x.get('percentageTokensHeld', 0.00):.2f}%</code>
<a href="https://dexscreener.com/ethereum/{first_by_x['contractaddress']}"><i>dex</i></a>

<b>💰 Most Profit:</b> 
<b>{next(iter(sortbyprofit))}</b> 
<a href="https://etherscan.io/address/{first_by_profit['contractaddress']}"><i>{first_by_profit['contractaddress']}</i></a>
🟢 Buys: <code>{first_by_profit['noOfBuys']}</code> 
🔴 Sells: <code>{first_by_profit['noOfSells']}</code>
➡️ Eth Spent:<code> {first_by_profit['totalEthSpent'] + first_by_profit['buyGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(first_by_profit['totalEthSpent'] + first_by_profit['buyGasTotal']):,.2f}</code>
⬅️ Eth Gained:<code> {first_by_profit['totalEthGained'] - first_by_profit['sellGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(first_by_profit['totalEthGained'] - first_by_profit['sellGasTotal']):,.2f}</code>
🚀 X's: <code>{first_by_profit['profitInXIncludingGas']:.2f} X</code> 
🔴 Tokens Sold: <code>{first_by_profit.get('percentageTokensSold', 0.00):.2f}%</code>
💎 Tokens Left: <code>{first_by_profit.get('percentageTokensHeld', 0.00):.2f}%</code>
<a href="https://dexscreener.com/ethereum/{first_by_profit['contractaddress']}"><i>dex</i></a>

<b>🔄 Most Transactions:</b> 
<b>{next(iter(sorttotaltx))}</b>
<a href="https://etherscan.io/address/{first_by_tx['contractaddress']}"><i>{first_by_tx['contractaddress']}</i></a>
🟢 Buys: <code>{first_by_tx['noOfBuys']}</code> 
🔴 Sells: <code>{first_by_tx['noOfSells']}</code>
➡️ Eth Spent<code>: {first_by_tx['totalEthSpent'] + first_by_tx['buyGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(first_by_tx['totalEthSpent'] + first_by_tx['buyGasTotal']):,.2f}</code>
⬅️ Eth Gained<code>: {first_by_tx['totalEthGained'] - first_by_tx['sellGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(first_by_tx['totalEthGained'] - first_by_tx['sellGasTotal']):,.2f}</code>
🚀 X's: <code>{first_by_tx['profitInXIncludingGas']:.2f}X</code> 
🔴 Tokens Sold: <code>{first_by_tx.get('percentageTokensSold', 0.00):.2f}%</code>
💎 Tokens Left: <code>{first_by_tx.get('percentageTokensHeld', 0.00):.2f}%</code>
<a href="https://dexscreener.com/ethereum/{first_by_tx['contractaddress']}"><i>dex</i></a>

<i>Disclaimer: This summary includes transactions of tokens bought/sold with ETH/WETH only. Gains/losses include gas fees. USD values use the current ETH price at request time. This summary may not cover all activities, please verify with your own records.</i>
"""
      
    #print(telegram_string)
    return telegram_string






async def top_tokens_profit(address):
    ethprice = get_eth_price()
    swaps = await get_token_swaps(address)
    swaps,skipped = assign_transaction_type(swaps)
    sortbyx,sortbyprofit,sorttotaltx = sort_updated_dict(swaps)

    top_token_strings = []
    for i, (token, token_data) in enumerate(islice(sortbyprofit.items(), 5)):
        token_string = f"""
<b>💰 #{i+1} Most Profit:</b> 
<b>{token}</b> 
<a href="https://etherscan.io/address/{token_data['contractaddress']}"><i>{token_data['contractaddress']}</i></a>
🟢 Buys: <code>{token_data['noOfBuys']}</code> 
🔴 Sells: <code>{token_data['noOfSells']}</code>
➡️ Eth Spent:<code> {token_data['totalEthSpent'] + token_data['buyGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(token_data['totalEthSpent'] + token_data['buyGasTotal']):,.2f}</code>
⬅️ Eth Gained:<code> {token_data['totalEthGained'] - token_data['sellGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(token_data['totalEthGained'] - token_data['sellGasTotal']):,.2f}</code>
🚀 X's: <code>{token_data['profitInXIncludingGas']:.2f} X</code> 
🔴 Tokens Sold: <code>{token_data.get('percentageTokensSold', 0.00):.2f}%</code>
💎 Tokens Left: <code>{token_data.get('percentageTokensHeld', 0.00):.2f}%</code>
<a href="https://dexscreener.com/ethereum/{token_data['contractaddress']}"><i>dex</i></a>
"""
        top_token_strings.append(token_string)
    return " \n".join(top_token_strings)


async def top_tokens_X(address):
    ethprice = get_eth_price()
    swaps = await get_token_swaps(address)
    swaps,skipped = assign_transaction_type(swaps)
    sortbyx,sortbyprofit,sorttotaltx = sort_updated_dict(swaps)

    top_token_strings = []
    for i, (token, token_data) in enumerate(islice(sortbyx.items(), 5)):
        token_string = f"""
<b>💰 #{i+1} Most X:</b> 
<b>{token}</b> 
<a href="https://etherscan.io/address/{token_data['contractaddress']}"><i>{token_data['contractaddress']}</i></a>
🟢 Buys: <code>{token_data['noOfBuys']}</code> 
🔴 Sells: <code>{token_data['noOfSells']}</code>
➡️ Eth Spent:<code> {token_data['totalEthSpent'] + token_data['buyGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(token_data['totalEthSpent'] + token_data['buyGasTotal']):,.2f}</code>
⬅️ Eth Gained:<code> {token_data['totalEthGained'] - token_data['sellGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(token_data['totalEthGained'] - token_data['sellGasTotal']):,.2f}</code>
🚀 X's: <code>{token_data['profitInXIncludingGas']:.2f} X</code> 
🔴 Tokens Sold: <code>{token_data.get('percentageTokensSold', 0.00):.2f}%</code>
💎 Tokens Left: <code>{token_data.get('percentageTokensHeld', 0.00):.2f}%</code>
<a href="https://dexscreener.com/ethereum/{token_data['contractaddress']}"><i>dex</i></a>
"""
        top_token_strings.append(token_string)
    return " \n".join(top_token_strings)

async def top_tokens_txs(address):
    ethprice = get_eth_price()
    swaps = await get_token_swaps(address)
    swaps,skipped = assign_transaction_type(swaps)
    sortbyx,sortbyprofit,sorttotaltx = sort_updated_dict(swaps)

    top_token_strings = []
    for i, (token, token_data) in enumerate(islice(sorttotaltx.items(), 5)):
        token_string = f"""
<b>💰 #{i+1} Most Transactions:</b> 
<b>{token}</b> 
<a href="https://etherscan.io/address/{token_data['contractaddress']}"><i>{token_data['contractaddress']}</i></a>
🟢 Buys: <code>{token_data['noOfBuys']}</code> 
🔴 Sells: <code>{token_data['noOfSells']}</code>
➡️ Eth Spent:<code> {token_data['totalEthSpent'] + token_data['buyGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(token_data['totalEthSpent'] + token_data['buyGasTotal']):,.2f}</code>
⬅️ Eth Gained:<code> {token_data['totalEthGained'] - token_data['sellGasTotal']:.4f} ETH</code>
┗ <code>${ethprice*(token_data['totalEthGained'] - token_data['sellGasTotal']):,.2f}</code>
🚀 X's: <code>{token_data['profitInXIncludingGas']:.2f} X</code> 
🔴 Tokens Sold: <code>{token_data.get('percentageTokensSold', 0):.2f}%</code>
💎 Tokens Left: <code>{token_data.get('percentageTokensHeld', 0.00):.2f}%</code>
<a href="https://dexscreener.com/ethereum/{token_data['contractaddress']}"><i>dex</i></a>
"""

        top_token_strings.append(token_string)
    return " \n".join(top_token_strings)




def sort_updated_dict(updated_dict):
    # Sort by X's (profit/loss ratio including gas)
    sorted_by_X = dict(sorted(updated_dict.items(), key=lambda item: item[1]['profitInXIncludingGas'], reverse=True))
    
    # Sort by Profit (profit/loss including gas)
    sorted_by_profit = dict(sorted(updated_dict.items(), key=lambda item: item[1]['profitLossIncludingGas'], reverse=True))
    
    # Sort by Total Transactions
    sorted_by_total_transactions = dict(sorted(updated_dict.items(), key=lambda item: item[1]['noOfBuys'] + item[1]['noOfSells'], reverse=True))

    return sorted_by_X, sorted_by_profit, sorted_by_total_transactions
   

def address_analysis_v2(token_dict):

    tokens_bought = len(token_dict)
    profitable_tokens = len([token for token in token_dict.values() if token['profitInXIncludingGas'] > 1])
    unprofitable_tokens = tokens_bought - profitable_tokens
    profitable_tokens_percentage = (profitable_tokens / tokens_bought) * 100 if tokens_bought else 0
    unprofitable_token_percentage = (unprofitable_tokens / tokens_bought)* 100 if tokens_bought else 0

    total_eth_spent = sum(token_data['totalEthSpent'] for token_data in token_dict.values())
    total_buy_gas_fees = sum(token_data['buyGasTotal'] for token_data in token_dict.values())
    total_eth_spent_including_buy_gas = total_eth_spent + total_buy_gas_fees

    total_eth_gained = sum(token_data['totalEthGained'] for token_data in token_dict.values())
    total_sell_gas_fees = sum(token_data['sellGasTotal'] for token_data in token_dict.values())
    total_eth_gained_including_sell_gas = total_eth_gained - total_sell_gas_fees

    profit_rating = (total_eth_gained / total_eth_spent) * 100
    profit_rating_including_gas = (total_eth_gained_including_sell_gas / total_eth_spent_including_buy_gas) * 100

    loss_rating = 100 - profit_rating
    loss_rating_including_gas = 100 - profit_rating_including_gas

    transactions_dates = [
        datetime.strptime(token_data["firstTxTime"], "%Y-%m-%d %H:%M:%S") 
        for token_data in token_dict.values()
    ]
    transactions_day_of_week = [date.weekday() for date in transactions_dates]
    most_active_day_of_week = Counter(transactions_day_of_week).most_common(1)[0][0]

    total_days = (max(transactions_dates) - min(transactions_dates)).days
    average_daily_gas_spend = total_buy_gas_fees / total_days if total_days != 0 else 0
    average_weekly_gas_spend = average_daily_gas_spend * 7

    average_gas_spent_per_token = total_buy_gas_fees / tokens_bought
    average_token_buys_per_week = tokens_bought / ((total_days / 7) if total_days >= 7 else 1)


    average_xs = median(token_data['profitInXIncludingGas'] for token_data in token_dict.values())
    average_eth_spent_per_token = total_eth_spent / tokens_bought
    average_eth_spent_per_token_including_buyfee = total_eth_spent_including_buy_gas / tokens_bought
    average_eth_gained_per_token = total_eth_gained / tokens_bought
    average_eth_gained_per_token_including_sellfee = total_eth_gained_including_sell_gas / tokens_bought

    averagePercentOfTokensSoldPerSell = mean(token_data.get("averagePercentOfTokensSoldPerSell", 0) for token_data in token_dict.values())
    
    total_eth_profit_loss = total_eth_gained_including_sell_gas - total_eth_spent_including_buy_gas
    total_roi = (total_eth_gained_including_sell_gas / total_eth_spent_including_buy_gas - 1) * 100
    profitable_investment_ratio = (profitable_tokens / tokens_bought) * 100
    average_profit_loss_per_token = (total_eth_gained_including_sell_gas - total_eth_spent_including_buy_gas) / tokens_bought
    net_profit_percentage = (total_eth_profit_loss / total_eth_spent_including_buy_gas) * 100
    average_gas_spend_ratio = (total_buy_gas_fees / total_eth_spent) * 100

    return {
        "most_active_day_of_week": most_active_day_of_week,
        "tokens_bought": tokens_bought,
        "profitable_tokens": profitable_tokens,
        "profitable_tokens_percentage": profitable_tokens_percentage,
        "unprofitable_token_percentage": unprofitable_token_percentage,
        "total_eth_spent": total_eth_spent,
        "total_buy_gas_fees": total_buy_gas_fees,
        "total_eth_spent_including_buy_gas": total_eth_spent_including_buy_gas,
        "total_eth_gained": total_eth_gained,
        "total_sell_gas_fees": total_sell_gas_fees,
        "total_eth_gained_including_sell_gas": total_eth_gained_including_sell_gas,
        "profit_rating": profit_rating,
        "profit_rating_including_gas": profit_rating_including_gas,
        "loss_rating": loss_rating,
        "loss_rating_including_gas": loss_rating_including_gas,
        "average_daily_gas_spend": average_daily_gas_spend,
        "average_weekly_gas_spend": average_weekly_gas_spend,
        "average_gas_spent_per_token": average_gas_spent_per_token,
        "average_token_buys_per_week": average_token_buys_per_week,
        "average_xs": average_xs,
        "average_eth_spent_per_token": average_eth_spent_per_token,
        "average_eth_spent_per_token_including_buyfee": average_eth_spent_per_token_including_buyfee,
        "average_eth_gained_per_token": average_eth_gained_per_token,
        "average_eth_gained_per_token_including_sellfee": average_eth_gained_per_token_including_sellfee,
        "averagePercentOfTokensSoldPerSell": averagePercentOfTokensSoldPerSell,
        "total_eth_profit_loss": total_eth_profit_loss,
        "total_roi": total_roi,
        "profitable_investment_ratio": profitable_investment_ratio,
        "average_profit_loss_per_token": average_profit_loss_per_token,
        "net_profit_percentage": net_profit_percentage,
        "average_gas_spend_ratio": average_gas_spend_ratio,
    }


def address_analysis(updated_dict): # I think this is all wrong
    eth_spent = []
    eth_gained = []
    buys_per_week = []
    gas_per_day = []
    transactions_dates = []
    profits = []
    losses = []
    gains = []
    buys_dates = []
    sells_dates = []
    total_gas_spent = 0

    for token_data in updated_dict.values():
        eth_spent.append(token_data["totalEthSpent"])
        eth_gained.append(token_data["totalEthGained"])

        for buy in token_data["Buys"]:
            transactions_dates.append(datetime.fromtimestamp(int(buy["timeStamp"])).date())
            gas_per_day.append(buy["gasFee"])
            losses.append(buy["swapWithDeci"] + buy["gasFee"])
            buys_dates.append(datetime.fromtimestamp(int(buy["timeStamp"])).date())
            total_gas_spent += buy["gasFee"]

        for sell in token_data["Sells"]:
            transactions_dates.append(datetime.fromtimestamp(int(sell["timeStamp"])).date())
            gas_per_day.append(sell["gasFee"])
            gains.append(sell["gainWithDeci"] - sell["gasFee"])
            sells_dates.append(datetime.fromtimestamp(int(sell["timeStamp"])).date())
            total_gas_spent += sell["gasFee"]

    if buys_dates:
        weeks = (max(buys_dates) - min(buys_dates)).days / 7
    else:
        weeks = 1  # Or some default value

    transactions_per_day = Counter(transactions_dates)
    transactions_per_weekday = [0]*7
    for date, count in transactions_per_day.items():
        transactions_per_weekday[date.weekday()] += count

    most_active_weekday = transactions_per_weekday.index(max(transactions_per_weekday))
    most_active_weekday_count = max(transactions_per_weekday)
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    tokens_bought = len(updated_dict)
    profitable_tokens = sum(1 for token_data in updated_dict.values() if token_data['profitLossIncludingGas'] > 0)

    stats = {
        "most_active_day_of_week": weekdays[most_active_weekday],
        "most_active_day_of_week_count": most_active_weekday_count,
        "tokens_bought": tokens_bought,
        "profitable_tokens": profitable_tokens,
        "profitable_tokens_percentage": (profitable_tokens / tokens_bought * 100) if tokens_bought else 0,
        "total_eth_spent": sum(eth_spent),
        "total_eth_gained": sum(eth_gained),
        "profit_rating": sum(gains) / sum(eth_spent) * 100 if eth_spent else 0,
        "loss_rating": sum(losses) / sum(eth_spent) * 100 if eth_spent else 0,
        "average_daily_gas_spend": mean(gas_per_day),
        "average_weekly_gas_spend": mean(gas_per_day) * 7,
        "average_gas_spent_per_token": total_gas_spent / len(updated_dict),
        "average_token_buys_per_week": len(buys_dates) / weeks if weeks else 0,
        "average_xs": mean(gains) / mean(eth_spent) if eth_spent else 0,
        "average_eth_spent_per_token": mean(eth_spent),
        "average_eth_gained_per_token": mean(eth_gained),
    }

   
    # New print statements


    print("Profit Rating: {:.2f}% - For every ETH spent on buying, you gained this percent back in returns.".format(stats["profit_rating"]))
    print("Loss Rating: {:.2f}% - For every ETH spent on buying, you lost this percent considering the total cost (token cost + gas fee).".format(stats["loss_rating"]))



    return stats


    
    
def calculate_token_statistics(ethswaps, eth_to_usd):
    token_statistics = []

    for token in ethswaps:
        total_eth_spent = 0
        total_eth_gained = 0
        total_gas = 0
        total_tokens_bought = 0
        total_tokens_sold = 0
        total_buys = 0
        total_sells = 0

        for transaction in ethswaps[token]:
            if transaction['transactionType'] == 'Buy':
                total_eth_spent += transaction['swappedDeci'] + transaction['totalGas']
                total_gas += transaction['totalGas']
                total_tokens_bought += transaction['gainedDeci']
                total_buys += 1
            elif transaction['transactionType'] == 'Sell':
                total_eth_gained += transaction['gainedDeci'] - transaction['totalGas']
                total_gas += transaction['totalGas']
                total_tokens_sold += transaction['swappedDeci']
                total_sells += 1

        gain_loss = total_eth_gained - total_eth_spent
        gain_loss_x = total_eth_gained / total_eth_spent if total_eth_spent > 0 else float('inf')

        total_tokens_remaining = total_tokens_bought - total_tokens_sold
        tokens_spent_percentage = total_tokens_sold / total_tokens_bought * 100 if total_tokens_bought > 0 else 0
        tokens_remaining_percentage = 100 - tokens_spent_percentage

        token_statistic = {
            'token': token,
            'total_eth_spent': total_eth_spent,
            'total_eth_spent_usd': total_eth_spent * eth_to_usd,
            'total_eth_gained': total_eth_gained,
            'total_eth_gained_usd': total_eth_gained * eth_to_usd,
            'gain_loss': gain_loss,
            'gain_loss_usd': gain_loss * eth_to_usd,
            'total_gas': total_gas,
            'total_gas_usd': total_gas * eth_to_usd,
            'gain_loss_x': gain_loss_x,
            'tokens_spent_percentage': tokens_spent_percentage,
            'tokens_remaining_percentage': tokens_remaining_percentage,
            'total_buys': total_buys,
            'total_sells': total_sells,
        }
        token_statistics.append(token_statistic)

    # Sort token_statistics by gain_loss_x in descending order
    token_statistics_sorted_by_x = sorted(token_statistics, key=lambda x: x['gain_loss_x'], reverse=True)

    # Format values to strings after sorting
    for statistic in token_statistics:
        statistic['total_eth_spent'] = "{:.2f} ETH (${:,.2f} USD)".format(statistic['total_eth_spent'], statistic['total_eth_spent_usd'])
        statistic['total_eth_gained'] = "{:.2f} ETH (${:,.2f} USD)".format(statistic['total_eth_gained'], statistic['total_eth_gained_usd'])
        statistic['gain_loss'] = "{:.2f} ETH (${:,.2f} USD)".format(statistic['gain_loss'], statistic['gain_loss_usd'])
        statistic['total_gas'] = "{:.3f} ETH (${:,.2f} USD)".format(statistic['total_gas'], statistic['total_gas_usd'])
        statistic['gain_loss_x'] = "{:.2f}".format(statistic['gain_loss_x'])
        statistic['tokens_spent_percentage'] = "{:.2f}".format(statistic['tokens_spent_percentage'])
        statistic['tokens_remaining_percentage'] = "{:.2f}".format(statistic['tokens_remaining_percentage'])

    return token_statistics, token_statistics_sorted_by_x








    

def calculate_gains_losses(token_dict_flat):
    gains = []
    losses = []
    total_gas = 0
    total_buys = 0  # Initialize total buys counter
    total_sells = 0  # Initialize total sells counter
    profitable_tokens = 0
    eth_price = get_eth_price()

    for token, swaps in token_dict_flat.items():
        eth_swaps = [swap for swap in swaps if ('ETH' in (swap['swappedToken'], swap['gainedToken']) and 'USD Coin' not in (swap['swappedToken'], swap['gainedToken']))]
        
        if eth_swaps:
            sorted_swaps = sorted(eth_swaps, key=lambda k: k['timeStamp'])
            buy_swaps = [swap for swap in sorted_swaps if swap['transactionType'] == 'Buy']
            sell_swaps = [swap for swap in sorted_swaps if swap['transactionType'] == 'Sell']
            
            total_spent = sum(swap['swappedDeci'] + swap['totalGas'] for swap in buy_swaps)
            total_gas += sum(swap['totalGas'] for swap in buy_swaps)

            total_gained = sum(swap['gainedDeci'] - swap['totalGas'] for swap in sell_swaps)  # Subtract gas fees from the gained amount
            total_gas += sum(swap['totalGas'] for swap in sell_swaps)  # Add the gas fees from sell operations to the total_gas

            total_buys += len(buy_swaps)  
            total_sells += len(sell_swaps)  

            # Calculate gains and losses per token
            gain_loss = total_gained - total_spent
            if sell_swaps:  
                if gain_loss > 0:
                    gains.append(gain_loss)
                    profitable_tokens += 1
                else:
                    losses.append(abs(gain_loss))
            else:  
                losses.extend([buy['swappedDeci'] + buy['totalGas'] for buy in buy_swaps])

    # Compute statistics
    total_gain = sum(gains)
    total_gain_usd = total_gain * eth_price  # Convert total_gain to USD
    average_gain = total_gain / len(gains) if gains else 0
    total_loss = sum(losses)
    total_loss_usd = total_loss * eth_price
    total_gas_usd = total_gas * eth_price
    average_loss = total_loss / len(losses) if losses else 0
    total_transactions = len(gains + losses)
    total_tokens = len(token_dict_flat)

    # Compute percentages
    gain_percentage = len(gains) / total_transactions * 100 if gains else 0
    loss_percentage = len(losses) / total_transactions * 100 if losses else 0
    average_gain_percentage = average_gain / total_gain * 100 if total_gain != 0 else 0
    average_loss_percentage = average_loss / total_loss * 100 if total_loss != 0 else 0
    success_rate = gain_percentage

    # Compute net gain or loss
    net_gain_loss = total_gain - total_loss
    net_gain_loss_usd = net_gain_loss * eth_price

    # Compute average x's
    avg_xs = sum(gains) / sum(losses) if losses else 0

    stats = {
    'Transactions': {
        'Total Buys': format(total_buys, ',d'),
        'Total Sells': format(total_sells, ',d'),
        'Number of Tokens Bought': format(total_tokens, ',d'),
        'Number of Profitable Tokens': format(profitable_tokens, ',d'),
    },
    'Gain Metrics': {
        'Total Gain': f'{format(total_gain, ",.2f")} ETH (${format(total_gain_usd, ",.2f")} USD)',
        'Average Gain per Positive Transaction': f'{format(average_gain, ",.2f")} ETH (${format(average_gain * eth_price, ",.2f")} USD)',
        'Gain Transactions as a Percentage of Total Transactions': f'{format(gain_percentage, ",.2f")}%',
        'Average Gain as a Percentage of Total Gain': f'{format(average_gain_percentage, ",.2f")}%',
    },
    'Loss Metrics': {
        'Total Loss': f'{format(total_loss, ",.2f")} ETH (${format(total_loss_usd, ",.2f")} USD)',
        'Average Loss per Negative Transaction': f'{format(average_loss, ",.2f")} ETH (${format(average_loss * eth_price, ",.2f")} USD)',
        'Loss Transactions as a Percentage of Total Transactions': f'{format(loss_percentage, ",.2f")}%',
        'Average Loss as a Percentage of Total Loss': f'{format(average_loss_percentage, ",.2f")}%',
    },
    'Net Results': {
        'Net Gain/Loss': f'{format(net_gain_loss, ",.2f")} ETH (${format(net_gain_loss_usd, ",.2f")} USD)',
        'Success Rate': f'{format(success_rate, ",.2f")}%',
    },
    'Gas Fees': {
        'Total Gas Fees': f'{format(total_gas, ",.2f")} ETH (${format(total_gas_usd, ",.2f")} USD)',
    },
    'Other Metrics': {
        'Average X': f'{format(avg_xs, ",.2f")}',
    }
}


    


    return stats




def telegram_post_format(gainslosses, statbyx, activetime, address):
    # Sort the statbyx list by 'gain_loss_x' in descending order
    stat_by_x_sorted = sorted(statbyx, key=lambda x: float(x['gain_loss_x']), reverse=True)
    # Token with the highest 'gain_loss_x'
    most_x_token = stat_by_x_sorted[0]
    
    # Sort the statbyx list by 'total_buys' in descending order
    stat_by_buys_sorted = sorted(statbyx, key=lambda x: x['total_buys'], reverse=True)
    # Token with the highest 'total_buys'
    most_traded_token = stat_by_buys_sorted[0]

    # Start creating the output string
    output_str = f"<b>{address}</b>\n"
    output_str += "<b>Trading Summary:</b>\n"
    output_str += "\n🔄 <b>Transactions</b>\n"
    output_str += f"┗ <code>Buys:</code> {gainslosses['Transactions']['Total Buys']}\n"
    output_str += f"┗ <code>Sells:</code> {gainslosses['Transactions']['Total Sells']}\n"
    output_str += f"┗ <code>Tokens Bought:</code> {gainslosses['Transactions']['Number of Tokens Bought']}\n"
    output_str += f"┗ <code>Profitable Tokens:</code> {gainslosses['Transactions']['Number of Profitable Tokens']}\n"

    output_str += "\n💰 <b>Gain Metrics</b>\n"
    output_str += f"┗ <code>Total Gain:</code> {gainslosses['Gain Metrics']['Total Gain']}\n"
    output_str += f"┗ <code>Avg Gain/Positive Tx:</code> {gainslosses['Gain Metrics']['Average Gain per Positive Transaction']}\n"
    output_str += f"┗ <code>Gain Tx %:</code> {gainslosses['Gain Metrics']['Gain Transactions as a Percentage of Total Transactions']}\n"
    output_str += f"┗ <code>Avg Gain %:</code> {gainslosses['Gain Metrics']['Average Gain as a Percentage of Total Gain']}\n"

    output_str += "\n💔 <b>Loss Metrics</b>\n"
    output_str += f"┗ <code>Total Loss:</code> {gainslosses['Loss Metrics']['Total Loss']}\n"
    output_str += f"┗ <code>Avg Loss/Negative Tx:</code> {gainslosses['Loss Metrics']['Average Loss per Negative Transaction']}\n"
    output_str += f"┗ <code>Loss Tx %:</code> {gainslosses['Loss Metrics']['Loss Transactions as a Percentage of Total Transactions']}\n"
    output_str += f"┗ <code>Avg Loss %:</code> {gainslosses['Loss Metrics']['Average Loss as a Percentage of Total Loss']}\n"

    output_str += "\n⚖️ <b>Net Results</b>\n"
    output_str += f"┗ <code>Net Gain/Loss:</code> {gainslosses['Net Results']['Net Gain/Loss']}\n"
    output_str += f"┗ <code>Success Rate:</code> {gainslosses['Net Results']['Success Rate']}\n"

    output_str += "\n⛽ <b>Gas Fees</b>\n"
    output_str += f"┗ <code>Gas Fees:</code> {gainslosses['Gas Fees']['Total Gas Fees']}\n"

    output_str += "\n📊 <b>Other Metrics</b>\n"
    output_str += f"┗ <code>Avg X's:</code> {gainslosses['Other Metrics']['Average X']}X\n"

    output_str += "\n🚀 <b>Most X's Token</b>\n"
    output_str += f"┗ <code>Token:</code> {most_x_token['token']}\n"
    output_str += f"┗ <code>Buys:</code> {most_x_token['total_buys']}\n"
    output_str += f"┗ <code>Sells:</code> {most_traded_token['total_sells']}\n"
    output_str += f"┗ <code>ETH Spent:</code> {most_x_token['total_eth_spent']}\n"
    output_str += f"┗ <code>ETH Gained:</code> {most_x_token['total_eth_gained']}\n"
    output_str += f"┗ <code>Gain/Loss X:</code> {most_x_token['gain_loss_x']}X\n"
    output_str += f"┗ <code>Tokens Left:</code> {most_x_token['tokens_remaining_percentage']}%\n"

    output_str += "\n💸 <b>Most Traded Token</b>\n"
    output_str += f"┗ <code>Token:</code> {most_traded_token['token']}\n"
    output_str += f"┗ <code>Buys:</code> {most_traded_token['total_buys']}\n"
    output_str += f"┗ <code>Sells:</code> {most_traded_token['total_sells']}\n"
    output_str += f"┗ <code>ETH Spent:</code> {most_traded_token['total_eth_spent']}\n"
    output_str += f"┗ <code>ETH Gained:</code> {most_traded_token['total_eth_gained']}\n"
    output_str += f"┗ <code>Gain/Loss X:</code> {most_traded_token['gain_loss_x']}X\n"
    output_str += f"┗ <code>Tokens Left:</code> {most_traded_token['tokens_remaining_percentage']}%\n"

    output_str += "\n⏰ <b>Active Trading Time</b>\n"
    output_str += f"┗ <code>{activetime}</code>\n\n"
    output_str += "<i>Disclaimer: This summary includes transactions of tokens bought/sold with ETH/WETH only. Gains/losses include gas fees. USD values use the current ETH price at request time. This summary may not cover all activities, please verify with your own records.</i>"

    #print(output_str)
    return output_str



def separate_swaps(token_dict_flat):

    """
    Categorizes swaps based on the type of transactions and whether they involve ETH.

    The function creates six categories:
        - ethSwaps: Tokens with buy and sell transactions involving ETH.
        - tokenToTokenSwaps: Tokens with buy and sell transactions that do not involve ETH.
        - mixedSwaps: Tokens with both types of transactions, some involving ETH and others not.
        - singleSwaps: Tokens with only one transaction.
        - onlyBuySwaps: Tokens with multiple transactions, all of which are buy transactions.
        - onlySellSwaps: Tokens with multiple transactions, all of which are sell transactions.

    Args:
        token_dict_flat (dict): A dictionary containing swaps associated with different tokens.

    Returns:
        tuple: A tuple containing six dictionaries. Each dictionary categorizes the swaps 
               based on the conditions mentioned above.
    """
    ethSwaps = {}
    tokenToTokenSwaps = {}
    mixedSwaps = {}
    singleSwaps = {}
    onlyBuySwaps = {}
    onlySellSwaps = {}

    for token, swaps in token_dict_flat.items():
        # Initialize swap and transaction type flags
        is_eth_swap, is_token_swap = False, False
        buy_count, sell_count = 0, 0

        for swap in swaps:
            # Check if swap involves ETH
            if swap['swappedToken'] == 'ETH' or swap['gainedToken'] == 'ETH':
                is_eth_swap = True
            else:
                is_token_swap = True

            # Count buy and sell transactions
            if swap['transactionType'] == 'Buy':
                buy_count += 1
            elif swap['transactionType'] == 'Sell':
                sell_count += 1

        # Categorize token based on swap and transaction types
        if len(swaps) == 1:
            singleSwaps[token] = swaps
        elif buy_count > 0 and sell_count == 0:
            onlyBuySwaps[token] = swaps
        elif sell_count > 0 and buy_count == 0:
            onlySellSwaps[token] = swaps
        elif is_eth_swap and not is_token_swap:
            ethSwaps[token] = swaps
        elif not is_eth_swap and is_token_swap:
            tokenToTokenSwaps[token] = swaps
        elif is_eth_swap and is_token_swap:
            mixedSwaps[token] = swaps

    return ethSwaps, tokenToTokenSwaps, mixedSwaps, singleSwaps, onlyBuySwaps, onlySellSwaps


  

def calculate_trading_behaviour(token_dict_flat, timeframe_start):
    total_hold_time = 0
    total_tokens = len(token_dict_flat)
    total_sell_transactions = 0
    total_profitable_sales = 0
    total_unprofitable_sales = 0
    longest_hold_before_profit = 0
    longest_hold_token = None
    longest_hold_eth_gained = None
    longest_hold_hash = None
    shortest_hold_before_profit = float('inf')
    shortest_hold_token = None
    shortest_hold_eth_gained = None
    shortest_hold_hash = None
    best_trade_profit = 0
    best_trade_token = None
    best_trade_buy_price = 0
    best_trade_sell_price = 0
    best_trade_hash_buy = None
    best_trade_hash_sell = None

    trading_style_counter = {
    "High-Frequency Trader": [],
    "Scalper": [],
    "Day Trader": [],
    "Swing Trader": [],
    "Short-Term Trader": [],
    "Mid-Term Trader": [],
    "Long-Term Trader": [],
    "Buy and Hold Investor": []
    }



    for token, transactions in token_dict_flat.items():
        if token in ['USDC', 'Tether','USD Coin']:
            continue

        buys = sorted([tx for tx in transactions if tx['transactionType'] == 'Buy'], key=lambda x: x['timeStamp'])
        sells = sorted([tx for tx in transactions if tx['transactionType'] == 'Sell'], key=lambda x: x['timeStamp'])
        total_sell_transactions += len(sells)

        for i in range(len(buys)):
            buy = buys[i]
            buy_time = int(buy['timeStamp'])

            if buy_time < timeframe_start:  # only consider buys within the timeframe
                continue

            if not sells:  # If there are no sells for this token
                current_time = int(time.time())
                hold_time = current_time - buy_time

                #if hold_time > 172800:  # If it's been more than 48 hours since the buy
                #    trading_style_counter['Rekt'].append({'token': token, 'hold_time': format_seconds_to_dhms(hold_time), 'bought': buy['swappedDeci'], 'sold': 0, 'buy_hash': buy['hash'], 'sell_hash': None, 'profit_loss_X': -buy['swappedDeci']})
            else:
                for sell in sells:
                    sell_time = int(sell['timeStamp'])

                    if sell_time < timeframe_start:  # only consider sells within the timeframe
                        continue

                    if sell_time > buy_time:  # only consider sells after the buy
                        hold_time = sell_time - buy_time
                        total_hold_time += hold_time
                        profit = sell['gainedDeci'] - buy['swappedDeci']

                        if profit > 0:  # if the sale was at a higher price
                            total_profitable_sales += 1
                            if profit > best_trade_profit:
                                best_trade_profit = profit
                                best_trade_token = token
                                best_trade_buy_price = buy['swappedDeci']
                                best_trade_sell_price = sell['gainedDeci']
                                best_trade_hash_buy = buy['hash']
                                best_trade_hash_sell = sell['hash']

                            if hold_time > longest_hold_before_profit:
                                longest_hold_before_profit = hold_time
                                longest_hold_token = token
                                longest_hold_eth_gained = sell['gainedDeci']
                                longest_hold_hash = sell['hash']
                            if hold_time < shortest_hold_before_profit:
                                shortest_hold_before_profit = hold_time
                                shortest_hold_token = token
                                shortest_hold_eth_gained = sell['gainedDeci']
                                shortest_hold_hash = sell['hash']

                        elif profit < 0:
                            total_unprofitable_sales += 1

                        # Categorize by hold time and sold percentage
                        sold_percentage = (sell['swappedDeci'] / buy['gainedDeci']) * 100
                        profit_loss_X = sell['gainedDeci'] - buy['swappedDeci']

                        #print(format_seconds_to_dhms(hold_time))

                        hold_times = [] # Create an empty list to store the hold times
                        hold_times.append(format_seconds_to_dhms_short(hold_time))# Append the hold_time to the hold_times list


                        if hold_time < 3600 and sold_percentage >= 90:
                            trading_style_counter['High-Frequency Trader'].append({'token': token, 'hold_time': format_seconds_to_dhms_short(hold_time), 'bought': buy['swappedDeci'], 'sold': sell['gainedDeci'], 'buy_hash': buy['hash'], 'sell_hash': sell['hash'], 'profit_loss_X': profit_loss_X})
                        elif hold_time < 10800 and sold_percentage >= 90:
                            trading_style_counter['Scalper'].append({'token': token, 'hold_time': format_seconds_to_dhms_short(hold_time), 'bought': buy['swappedDeci'], 'sold': sell['gainedDeci'], 'buy_hash': buy['hash'], 'sell_hash': sell['hash'], 'profit_loss_X': profit_loss_X})
                        elif hold_time < 21600 and sold_percentage >= 90:
                            trading_style_counter['Day Trader'].append({'token': token, 'hold_time': format_seconds_to_dhms_short(hold_time), 'bought': buy['swappedDeci'], 'sold': sell['gainedDeci'], 'buy_hash': buy['hash'], 'sell_hash': sell['hash'], 'profit_loss_X': profit_loss_X})
                        elif hold_time < 43200 and sold_percentage >= 90:
                            trading_style_counter['Swing Trader'].append({'token': token, 'hold_time': format_seconds_to_dhms_short(hold_time), 'bought': buy['swappedDeci'], 'sold': sell['gainedDeci'], 'buy_hash': buy['hash'], 'sell_hash': sell['hash'], 'profit_loss_X': profit_loss_X})
                        elif hold_time < 86400 and sold_percentage >= 90:
                            trading_style_counter['Short-Term Trader'].append({'token': token, 'hold_time': format_seconds_to_dhms_short(hold_time), 'bought': buy['swappedDeci'], 'sold': sell['gainedDeci'], 'buy_hash': buy['hash'], 'sell_hash': sell['hash'], 'profit_loss_X': profit_loss_X})
                        elif hold_time < 172800 and sold_percentage >= 90:
                            trading_style_counter['Mid-Term Trader'].append({'token': token, 'hold_time': format_seconds_to_dhms_short(hold_time), 'bought': buy['swappedDeci'], 'sold': sell['gainedDeci'], 'buy_hash': buy['hash'], 'sell_hash': sell['hash'], 'profit_loss_X': profit_loss_X})
                        elif hold_time >= 604800 and sold_percentage >= 90:
                            trading_style_counter['Buy and Hold Investor'].append({'token': token, 'hold_time': format_seconds_to_dhms_short(hold_time), 'bought': buy['swappedDeci'], 'sold': sell['gainedDeci'], 'buy_hash': buy['hash'], 'sell_hash': sell['hash'], 'profit_loss_X': profit_loss_X})
                        break


    
    hold_times.sort()

    n = len(hold_times)
    if n % 2 == 0:
        # If the number of hold times is even, average the two middle values
        median_index = n // 2
        median_value = (hold_times[median_index - 1] + hold_times[median_index]) / 2
    else:
        # If the number of hold times is odd, take the middle value
        median_index = n // 2
        median_value = hold_times[median_index]
        #average_hold_time = total_hold_time / total_sell_transactions if total_sell_transactions != 0 else 0
        

    trading_behaviour = {
        'average_hold_time': median_value,
        'total_tokens': total_tokens,
        'total_profitable_sales': total_profitable_sales,
        'total_unprofitable_sales': total_unprofitable_sales,
        'longest_hold_before_profit': {
            'token': longest_hold_token,
            'hold_time': format_seconds_to_dhms(longest_hold_before_profit),
            'eth_gained': longest_hold_eth_gained,
            'hash': longest_hold_hash
        },
        'shortest_hold_before_profit': {
            'token': shortest_hold_token,
            'hold_time': format_seconds_to_dhms(shortest_hold_before_profit),
            'eth_gained': shortest_hold_eth_gained,
            'hash': shortest_hold_hash
        },
        'best_trade': {
            'token': best_trade_token,
            'buy_price': best_trade_buy_price,
            'sell_price': best_trade_sell_price,
            'hash_buy': best_trade_hash_buy,
            'hash_sell': best_trade_hash_sell,
            'profit': best_trade_profit
        },
        'trading_style_counter': trading_style_counter
    }

    return trading_behaviour


    #return trading_behaviour




def format_seconds_to_dhms(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days} days {hours} hours {minutes} minutes {seconds} seconds"

def format_seconds_to_dhms_short(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    time_parts = []
    if days > 0:
        time_parts.append(f"{days} days")
    if hours > 0:
        time_parts.append(f"{hours} hours")
    if minutes > 0:
        time_parts.append(f"{minutes} minutes")
    if seconds > 0:
        time_parts.append(f"{seconds} seconds")

    return " ".join(time_parts)

def most_active_time_window(token_dict, window_size=2):
    windows = []

    # Collect all transactions across all tokens
    for token_name, transactions in token_dict.items():
        for hash, transaction_list in transactions.items():
            for transaction in transaction_list:
                # Convert the UNIX timestamp to a datetime object
                dt = datetime.utcfromtimestamp(int(transaction["timeStamp"]))

                # Assign the transaction to a time window
                window_start = dt.hour // window_size * window_size
                window_end = window_start + window_size

                # Normalize the window_end to not exceed 24 (24-hour clock)
                if window_end > 24:
                    window_end = 24

                # Format the window start and end times as strings
                window_start_str = f"{window_start:02d}:00"
                window_end_str = f"{window_end:02d}:00"

                # Add the time window to the list
                windows.append((window_start_str, window_end_str))

    # Count the occurrences of each time window
    window_counts = Counter(windows)

    # Find the two most common time windows
    most_common_windows = window_counts.most_common(2)

    # Format the windows as strings and combine them with a newline
    active_time_windows = "\n┗".join([f"{start} - {end}" for (start, end), _ in most_common_windows])

    return active_time_windows


def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return hours, minutes, seconds



async def return_wallet_summary_dict(address: str) -> dict:
    try:
        address = address.lower()
        ethprice = get_eth_price()
        swaps = await get_token_swaps(address)
        swaps,skipped = assign_transaction_type(swaps)
        sortbyx,sortbyprofit,sorttotaltx = sort_updated_dict(swaps)
        pf = address_analysis_v2(swaps)

        days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        # Helper function to construct top tokens data
        def construct_top_data(sorted_dict, ethprice):
            top_data = []
            for key in list(sorted_dict.keys())[:5]:  # Get the top 5 keys
                token = sorted_dict[key]
                top_data.append({
                    'name': key,
                    'contract_address': token['contractaddress'],
                    'buys': token['noOfBuys'],
                    'sells': token['noOfSells'],
                    'eth_spent': token['totalEthSpent'] + token['buyGasTotal'],
                    'eth_spent_usd': ethprice * (token['totalEthSpent'] + token['buyGasTotal']),
                    'eth_gained': token['totalEthGained'] - token['sellGasTotal'],
                    'eth_gained_usd': ethprice * (token['totalEthGained'] - token['sellGasTotal']),
                    'xs': token['profitInXIncludingGas'],
                    'tokens_sold_percentage': token.get('percentageTokensSold', 0.00),
                    'tokens_left_percentage': token.get('percentageTokensHeld', 0.00)
                })
            return top_data

        # Constructing the dictionary
        wallet_summary = {
            'address': address,
            'most_active_day_of_week': days_of_week[pf['most_active_day_of_week']],
            'tokens': {
                'purchased': pf['tokens_bought'],
                'profitable': pf['profitable_tokens'],
                'profitable_percentage': pf['profitable_tokens_percentage'],
                'unprofitable': pf['tokens_bought'] - pf['profitable_tokens'],
                'unprofitable_percentage': pf['unprofitable_token_percentage']
            },
            'transactions': {
                'eth_spent': pf['total_eth_spent_including_buy_gas'],
                'eth_spent_usd': pf['total_eth_spent_including_buy_gas']*ethprice,
                'eth_gained': pf['total_eth_gained_including_sell_gas'],
                'eth_gained_usd': pf['total_eth_gained_including_sell_gas']*ethprice
            },
            'averages': {
                'spend_per_token': pf['average_eth_spent_per_token_including_buyfee'],
                'spend_per_token_usd': pf['average_eth_spent_per_token_including_buyfee']*ethprice,
                'gain_per_token': pf['average_eth_gained_per_token_including_sellfee'],
                'gain_per_token_usd': pf['average_eth_gained_per_token_including_sellfee']*ethprice,
                'xs': pf['average_xs'],
                'gas_per_token': pf['average_gas_spent_per_token'],
                'gas_per_token_usd': pf['average_gas_spent_per_token']*ethprice,
                'bag_sold_percentage': pf['averagePercentOfTokensSoldPerSell']
            },
            'profits': {
                'rating': pf['profit_rating_including_gas'],
                'net': pf['net_profit_percentage'],
                'success_ratio': pf['profitable_investment_ratio']
            },
            'profit_loss': {
                'eth': pf['total_eth_profit_loss'],
                'usd': pf['total_eth_profit_loss']*ethprice,
                'roi': pf['total_roi']
            },
            'top_x_tokens': construct_top_data(sortbyx, ethprice),
            'top_profit_tokens': construct_top_data(sortbyprofit, ethprice),
            'top_transaction_tokens': construct_top_data(sorttotaltx, ethprice)
        }
        return wallet_summary
    except Exception as e:
        print("e")
        return(None)







if __name__ == "__main__":


    # Use your wallet address here
    #wallet_address = "0xf4A19737c437c7BcDdD98a41536bb14f8a521aA9".lower()
    #wallet_address = "0xf4A19737c437c7BcDdD98a41536bb14f8a521aA9"
    #result = asyncio.run(return_wallet_summary_dict(wallet_address))
    print("stressed as fuck")
    


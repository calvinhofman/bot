import os
import json
import gzip
from datetime import datetime, timedelta
import asyncio
from aiohttp import ClientSession


class WalletDataCache:
    ETHERSCAN_API_KEY = "UBY4ASSNTXWCZYURPKKATM1PKPNAWNTPTW"
    ETHERSCAN_API_URL = "https://api.etherscan.io/api"

    def __init__(self, save_path='walletdata.json'):
        print("Initializing WalletDataCache")
        self.save_path = save_path
        self.data = {}
        if os.path.exists(self.save_path):
            self.load_data()


    async def fetch_transactions(self, session, address, action):
        params = {
            "module": "account",
            "action": action,
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "sort": "asc",
            "page": 1,  # start from first page
            "offset": 10000,  # transactions per page (max limit)
            "apikey": self.ETHERSCAN_API_KEY
        }

        transactions = []
        retries = 5  # define the maximum number of retries
        backoff_factor = 0.1  # define the factor to use for backoff timing
        while True:
            #print(f"Fetching {action} page {params['page']} for address {address}")
            async with session.get(self.ETHERSCAN_API_URL, params=params) as response:
                # check if the status code is 429 Too Many Requests (rate limit exceeded)
                if response.status == 429:
                    if retries > 0:
                        # Wait for some time before retrying, with backoff
                        backoff_time = backoff_factor * (5 - retries) ** 2
                        print(f"Rate limit exceeded. Retrying in {backoff_time} seconds...")
                        await asyncio.sleep(backoff_time)
                        retries -= 1
                        continue  # skip the rest of the loop and try again
                    else:
                        print("Exhausted maximum number of retries. Aborting.")
                        break  # break out of the loop completely

                # If status is not 429, process the response
                data = await response.json()
                transactions.extend(data['result'])
                #print(f"Fetched {len(data['result'])} transactions. Total transactions fetched: {len(transactions)}")
                # If less than the offset transactions are returned, we've fetched all transactions
                if len(data['result']) < params['offset']:
                    break
                params['page'] += 1  # go to next page

                # If there was no rate limit exception, reset the retry counter
                retries = 5

        return transactions
            

    def save_data(self):
        #print("Saving data")
        with gzip.GzipFile(self.save_path, 'w') as file:
            file.write(json.dumps(self.data).encode('utf-8'))

    def load_data(self):
        print("Loading data from disk")
        if os.path.exists(self.save_path):
            with gzip.GzipFile(self.save_path, 'r') as file:
                self.data = json.loads(file.read().decode('utf-8'))

    def update_wallet_info(self, wallet_address, timestamp, tx_normal, tx_token, tx_internal):
        #print(f"Updating wallet info for {wallet_address}")
        self.data[wallet_address] = {
            'timestamp': timestamp,
            'tx_normal': tx_normal,
            'tx_token': tx_token,
            'tx_internal': tx_internal
        }
        self.save_data()

    def is_wallet_data_recent(self, wallet_address):
        #print(f"Checking if wallet data for {wallet_address} is recent")
        if wallet_address not in self.data:
            return False
        time_difference = datetime.now() - datetime.fromisoformat(self.data[wallet_address]['timestamp'])
        return time_difference < timedelta(hours=3)

    def get_wallet_data(self, wallet_address):
        #print(f"Getting wallet data for {wallet_address}")
        return self.data.get(wallet_address, None)
    
    

    async def update_data_if_needed(self, session, wallet_address):
        #print(f"Updating data if needed for {wallet_address}")
        if not self.is_wallet_data_recent(wallet_address):
            print(f"Fetching transactions for {wallet_address}")
            tx_normal = await self.fetch_transactions(session, wallet_address, "txlist")
            tx_token = await self.fetch_transactions(session, wallet_address, "tokentx")
            tx_internal = await self.fetch_transactions(session, wallet_address, "txlistinternal")
            self.update_wallet_info(wallet_address, datetime.now().isoformat(), tx_normal, tx_token, tx_internal)
        return self.get_wallet_data(wallet_address)

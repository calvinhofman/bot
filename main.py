import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web3 import Web3

import tokenfolio as tf

app = FastAPI(title='0xwallet')


# Configure CORS
origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",  # Add more allowed origins if needed
    "https://0xwallet.io",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get('/api/wallet/')
async def query_wallet(wallet_address: str) -> dict:
    if not wallet_address:
        return {
            'error': 'Missing parameter "walletAddress"'
        }
    else:
        if not Web3.is_address(wallet_address):
            return {
                "error": f"{wallet_address} is invalid"
            }
        else:
            wallet_address = Web3.to_checksum_address(wallet_address)
            return {
                'result': await tf.return_wallet_summary_dict(wallet_address)
            }
            

uvicorn.run(app, host='178.63.133.204', port=8080)
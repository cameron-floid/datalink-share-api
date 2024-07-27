from fastapi import FastAPI, HTTPException, Request
from typing import List
from hashlib import sha256
from collections import Counter
from datetime import datetime, timezone
import json
import os

from app.models import MessageSender, Message, Block, ChainProposal, Participant

app = FastAPI()

# File paths
CHAIN_FILE = 'data/blockchain.json'
PARTICIPANTS_FILE = 'data/participants.json'


# Load existing data if available
def load_data():
    global chains, participants

    if os.path.exists(CHAIN_FILE):
        with open(CHAIN_FILE, 'r') as f:
            data = json.load(f)
            chains = data.get('chains', [])
    else:
        chains = []

    if os.path.exists(PARTICIPANTS_FILE):
        with open(PARTICIPANTS_FILE, 'r') as f:
            data = json.load(f)
            participants = set((p['ipAddress'], p['uuid']) for p in data.get('participants', []))
    else:
        participants = set()

load_data()

@app.post("/share-latest-chain")
async def share_latest_chain(request: Request, proposal: ChainProposal):
    global chains

    # Validate the proposed chain
    if not is_chain_valid(proposal.blocks):
        raise HTTPException(status_code=400, detail="Invalid chain")

    # Add the proposal to the list of chains
    chains.append(proposal.dict())

    # Determine the majority chain
    latest_chain = get_majority_chain()

    # Save the updated chain to file
    save_chain()

    return {"status": "success", "latest_chain": latest_chain}

@app.get("/get-latest-chain")
async def get_latest_chain():
    if not chains:
        return {"status": "success", "latest_chain": {}}

    latest_chain = get_majority_chain()
    return {"status": "success", "latest_chain": latest_chain}

@app.get("/index")
async def index():
    latest_chain = get_majority_chain() if chains else {}
    return {
        "status": "success",
        "participants": list(participants),
        "latest_chain": latest_chain
    }

@app.post("/create-genesis")
async def create_genesis():
    global chains, participants

    if chains or participants:
        raise HTTPException(status_code=400, detail="Blockchain or participants already initialized")

    # Create genesis block
    genesis_block = Block(
        index=1,
        previousHash="0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=Message(
            sender=MessageSender(ipAddress="0.0.0.0", uuid="00000000-0000-0000-0000-000000000000"),
            recipient=MessageSender(ipAddress="0.0.0.0", uuid="00000000-0000-0000-0000-000000000000"),
            content="Genesis block",
            timestamp=datetime.now(timezone.utc).isoformat()
        ),
        proof=0,
        hash="0"  # Genesis block hash
    )

    # Initialize blockchain with genesis block
    initial_chain = {
        "blocks": [genesis_block.dict()],
        "network": {
            "nodes": [],
            "version": "1.0.0",
            "lastUpdated": datetime.now(timezone.utc).isoformat()
        },
        "status": {"isValid": True, "error": None}
    }
    chains.append(initial_chain)

    # Save initial data to files
    save_chain()
    save_participants()

    return {"status": "success", "message": "Genesis block created and blockchain initialized"}

@app.post("/send-message")
async def send_message(message: Message):
    # Ensure the message has valid participants
    if not (message.sender and message.recipient):
        raise HTTPException(status_code=400, detail="Sender and recipient information is required")

    # Check if the sender's and receiver's uuid and ipAddress's are valid, else raise exception
    sender = (message.sender.ipAddress, message.sender.uuid)
    receiver = (message.recipient.ipAddress, message.recipient.uuid)

    if sender not in participants or receiver not in participants:
        raise HTTPException(status_code=400, detail="Sender or recipient is not a registered participant")

    # Create a new block for the message
    previous_block = chains[-1]['blocks'][-1] if chains else None
    new_index = (previous_block['index'] + 1) if previous_block else 1

    new_block = Block(
        index=new_index,
        previousHash=calculate_hash(Block(**previous_block)) if previous_block else "0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=message,
        proof=0,  # This would be replaced with actual proof in a real implementation
        hash=""  # The hash will be set after computing it
    )

    # Compute the hash for the new block
    new_block.hash = calculate_hash(new_block)

    # Add the new block to the blockchain
    if chains:
        chains[-1]['blocks'].append(new_block.dict())
    else:
        chains.append({
            "blocks": [new_block.dict()],
            "network": {"nodes": [], "version": "1.0.0", "lastUpdated": datetime.now(timezone.utc).isoformat()},
            "status": {"isValid": True, "error": None}
        })

    # Save the updated chain to file
    save_chain()

    return {"status": "success", "message": "Message added to blockchain"}

@app.post("/register-participant")
async def register_participant(participant: Participant):
    global participants

    try:
        # Convert the participant to a tuple for easier set operations
        participant_tuple = (participant.ipAddress, participant.uuid)

        # Check if the participant is already registered
        if participant_tuple in participants:
            raise HTTPException(status_code=400, detail="Participant already registered")

        # Add the participant to the set and save to file
        participants.add(participant_tuple)
        save_participants()

        return {"status": "success", "message": "Participant registered successfully"}

    except Exception as e:
        # Log the error for debugging
        return {"status": "error", "message": str(e)}

def is_chain_valid(blocks: List[Block]) -> bool:
    if len(blocks) == 0:
        return False

    # Check if genesis block is valid
    if blocks[0].index != 1 or blocks[0].previousHash != "0" or blocks[0].hash != calculate_hash(blocks[0]):
        return False

    # Validate the chain starting from the second block
    for i in range(1, len(blocks)):
        current = blocks[i]
        previous = blocks[i - 1]

        if current.previousHash != calculate_hash(previous):
            return False

        if current.hash != calculate_hash(current):
            return False

    return True

def calculate_hash(block: Block) -> str:
    block_string = json.dumps({
        "index": block.index,
        "previousHash": block.previousHash,
        "timestamp": block.timestamp,
        "message": block.message.dict(),
        "proof": block.proof
    }, sort_keys=True).encode()
    return sha256(block_string).hexdigest()

def get_majority_chain() -> dict:
    if not chains:
        return {}

    # Find the most common chain
    chains_str = [json.dumps(chain, sort_keys=True) for chain in chains]
    most_common_chain_str, _ = Counter(chains_str).most_common(1)[0]
    return json.loads(most_common_chain_str)

def save_chain():
    with open(CHAIN_FILE, 'w') as f:
        json.dump({"chains": chains}, f, indent=4)

def save_participants():
    with open(PARTICIPANTS_FILE, 'w') as f:
        # Convert participants back to list of dicts for JSON serialization
        participants_list = [{"ipAddress": p[0], "uuid": p[1]} for p in participants]
        json.dump({"participants": participants_list}, f, indent=4)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

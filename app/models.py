from pydantic import BaseModel
from typing import List


class MessageSender(BaseModel):
    ipAddress: str
    uuid: str


class Message(BaseModel):
    sender: MessageSender
    recipient: MessageSender
    content: str
    timestamp: str


class Block(BaseModel):
    index: int
    previousHash: str
    timestamp: str
    message: Message
    proof: int
    hash: str


class ChainProposal(BaseModel):
    blocks: List[Block]
    network: dict
    status: dict


class Participant(BaseModel):
    ipAddress: str
    uuid: str

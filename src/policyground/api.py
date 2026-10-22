"""`POST /ask {tenant, question}` -> cited answer."""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

from policyground.graph import ask, build  # noqa: E402  (needs env loaded first)

app = FastAPI(title="PolicyGround")
graph = build()


class AskRequest(BaseModel):
    tenant: str
    question: str


class AskResponse(BaseModel):
    answer: str
    citations: list[str]
    abstain: bool
    input_tokens: int
    output_tokens: int


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    state = ask(graph, req.tenant, req.question)
    return AskResponse(**{k: state[k] for k in AskResponse.model_fields})

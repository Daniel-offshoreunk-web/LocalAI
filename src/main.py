import httpx
from fastapi import FastAPI, Request, Response, HTTPException

app = FastAPI(title="Secure Gatway")

vllm_backend = "localost:8080"

@app.get("/health")
async def health_check():
    """Health check to confirm it is running"""
    return {"status": "healthy", "gateway": "operational"}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Need to add security protocols to this
    Will respond to any reqeust and will not scan output or input"""
    client_host = request.client.host
    raw_body = await request.body
    async with httpx.AsyncClient as client:
        try:
            vllm_response = client.post(
                f"{vllm_backend}/v1/chat/completions",
                headers=dict(request.headers),
                content=raw_body,
                timeout=60.0
            )
            return Response(
                content=vllm_response.content,
                status_code=vllm_response.status_code,
                headers=dict(vllm_response.headers)
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, details=f"VLLM unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
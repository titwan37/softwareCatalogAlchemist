import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes.software_catalog import router as catalog_router

app = FastAPI(
    title="Software Catalog Alchemist",
    description="Transform disorganized software archives into structured, searchable catalogs",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(catalog_router)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "softwareCatalogAlchemist"}


# Mount static assets (js, css, components) under /static or root
app.mount("/components", StaticFiles(directory="frontend/components"), name="components")
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")


# Catch-all to serve index.html for SPA routing
@app.get("/{path:path}")
async def catch_all(path: str):
    file_path = f"frontend/{path}"
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse("frontend/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

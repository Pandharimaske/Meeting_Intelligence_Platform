import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level,
    )

"""
AWS Lambda handler for the FastAPI application.
Uses Mangum to wrap the ASGI app for Lambda compatibility.
"""

from mangum import Mangum

from src.app.api import app

# Create the Lambda handler
handler = Mangum(app, lifespan="off")

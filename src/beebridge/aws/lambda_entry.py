"""AWS Lambda entry point (AWS Builder): wraps the FastAPI app with Mangum
when deployed via infra/aws/template.yaml. Local runs use uvicorn instead.
"""
try:
    from mangum import Mangum
    from ..main import app
    handler = Mangum(app)
except ImportError:  # mangum is a deploy-only dependency
    def handler(event, context=None):  # pragma: no cover
        return {"statusCode": 500, "body": "mangum not installed in this environment"}

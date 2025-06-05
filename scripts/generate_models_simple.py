#!/usr/bin/env python3
"""
Simple script to fetch Paradex API OpenAPI spec and generate Pydantic models.

This script:
1. Fetches the Swagger 2.0 spec from Paradex API
2. Uses swagger2openapi to convert it to OpenAPI 3.0 format
3. Generates Pydantic models using datamodel-code-generator
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx


def main():
    """Main function to orchestrate the model generation."""
    api_url = "https://api.prod.paradex.trade/swagger/doc.json"
    output_dir = Path("paradex_py/api/generated")

    print("📡 Fetching OpenAPI spec from Paradex API...")

    # Fetch the spec
    with httpx.Client() as client:
        response = client.get(api_url)
        response.raise_for_status()
        swagger_spec = response.json()

    # Save swagger spec to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(swagger_spec, f, indent=2)
        swagger_file = f.name

    # Convert to OpenAPI 3.0 using swagger2openapi
    openapi_file = tempfile.mktemp(suffix=".json")

    try:
        print("🔄 Converting Swagger 2.0 to OpenAPI 3.0...")

        # Use npx to run swagger2openapi
        convert_cmd = ["npx", "--yes", "swagger2openapi", swagger_file, "--outfile", openapi_file, "--patch"]

        result = subprocess.run(convert_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Error converting spec: {result.stderr}")
            # Fallback: use the original swagger spec
            openapi_file = swagger_file
            print("⚠️  Using original Swagger spec as fallback")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        print("🔧 Generating Pydantic models...")

        # Generate models using datamodel-code-generator
        gen_cmd = [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            openapi_file,
            "--input-file-type",
            "openapi",
            "--output",
            str(output_dir),
            "--use-annotated",
            # "--use-field-description",
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--target-python-version",
            "3.9",
            "--use-schema-description",
            "--field-constraints",
            "--snake-case-field",
            "--disable-appending-item-suffix",
            "--use-union-operator",
            "--allow-population-by-field-name",
            "--allow-extra-fields",
            "--use-double-quotes",
            "--use-standard-collections",
        ]

        print(f"Running: {' '.join(gen_cmd)}")
        result = subprocess.run(gen_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ Error generating models: {result.stderr}")
            sys.exit(1)

        print(f"✅ Models generated successfully in {output_dir}")

        # Update __init__.py to import all models
        init_file = output_dir / "__init__.py"
        init_content = init_file.read_text() if init_file.exists() else ""

        if "from .model import *" not in init_content:
            init_file.write_text(
                f'{init_content}\n"""Generated API models from Paradex OpenAPI spec."""\n\n'
                "# ruff: noqa: F403, A003\n"
                "# Import all generated models\n"
                "from .model import *\n"
                "from .requests import *\n"
                "from .responses import *\n\n"
                "__all__ = [\n"
                "    # Re-export everything from sub-modules\n"
                "]\n"
            )

        print("🎉 Model generation completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    finally:
        # Cleanup temp files and generated spec
        Path(swagger_file).unlink(missing_ok=True)
        if openapi_file != swagger_file:
            Path(openapi_file).unlink(missing_ok=True)
        Path("openapi_spec.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

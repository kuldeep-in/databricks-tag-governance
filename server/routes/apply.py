from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from server.config import run_sql, WAREHOUSE_ID
from server.config_store import get_config

router = APIRouter()


class ApplyTagsRequest(BaseModel):
    catalog:     str
    schema:      str
    table:       str
    description: str = ""
    tags:        dict[str, str] = {}


@router.post("/apply-tags")
def apply_tags(req: ApplyTagsRequest):
    full_name = f"{req.catalog}.{req.schema}.{req.table}"
    errors = []

    cfg = get_config()
    if cfg is None:
        raise HTTPException(status_code=503, detail="App not configured. Please set up via the Settings page.")
    tag_columns = cfg.get("tag_columns", [])
    # Tags with values → SET; tags left empty in the form → UNSET (idempotent)
    desired  = {k: v for k, v in req.tags.items() if k in tag_columns and v.strip()}
    to_unset = [k for k in tag_columns if k not in desired]

    # Apply description
    if req.description is not None:
        safe_desc = req.description.replace("'", "\\'")
        try:
            run_sql(f"COMMENT ON TABLE {full_name} IS '{safe_desc}'", warehouse_id=WAREHOUSE_ID)
        except Exception as e:
            errors.append(f"description: {e}")

    # Set tags
    if desired:
        tag_str = ", ".join(f"'{k}' = '{v.replace(chr(39), chr(39)*2)}'" for k, v in desired.items())
        try:
            run_sql(f"ALTER TABLE {full_name} SET TAGS ({tag_str})", warehouse_id=WAREHOUSE_ID)
        except Exception as e:
            errors.append(f"set_tags: {e}")

    # Unset removed tags
    if to_unset:
        unset_str = ", ".join(f"'{k}'" for k in to_unset)
        try:
            run_sql(f"ALTER TABLE {full_name} UNSET TAGS ({unset_str})", warehouse_id=WAREHOUSE_ID)
        except Exception as e:
            errors.append(f"unset_tags: {e}")

    if errors:
        raise HTTPException(status_code=500, detail="; ".join(errors))

    return {"status": "ok", "table": full_name, "tags_set": list(desired.keys()), "tags_unset": to_unset}

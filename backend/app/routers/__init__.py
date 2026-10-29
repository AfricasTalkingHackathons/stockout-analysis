from fastapi import Query


def paginate(query, page: int, page_size: int, mapper):
    total = query.order_by(None).count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [mapper(r) for r in rows], "total": total, "page": page, "page_size": page_size}


PageQ = Query(1, ge=1, le=10_000)
SizeQ = Query(25, ge=1, le=100)

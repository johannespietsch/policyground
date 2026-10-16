# Init scripts are baked in rather than bind-mounted: Docker Desktop can't mount
# from ~/Documents without a macOS privacy grant, and baking also pins them.
FROM pgvector/pgvector:pg17
COPY init/ /docker-entrypoint-initdb.d/

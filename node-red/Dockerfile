FROM nodered/node-red:4.0

COPY --chown=node-red:root package.json /data/package.json
RUN cd /data && npm install --omit=dev --no-audit --no-fund

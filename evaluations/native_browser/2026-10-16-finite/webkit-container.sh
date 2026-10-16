#!/bin/sh
exec docker run --rm -i --init --network host --shm-size=256m --memory=1g \
  --mount type=bind,source=/home/g/.cache/ms-playwright/webkit-2359,target=/browser,readonly \
  --entrypoint /browser/pw_run.sh \
  sha256:59fe35832a79d1324e778b737760b2afc11cffcbaeba325012f96cabae832a75 "$@"

# base image
FROM registry.cn-hangzhou.aliyuncs.com/mr-docker-hub/node:20.11-alpine3.19 AS base
LABEL maintainer="lobyliang@gmail.com"

# if you located in China, you can use aliyun mirror to speed up
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories

RUN apk add --no-cache tzdata


# install packages
FROM base as packages

WORKDIR /app/web

COPY package.json .
COPY yarn.lock .

# RUN npm install yarn -g

# if you located in China, you can use taobao registry to speed up
RUN yarn install --registry https://registry.npmmirror.com/

# RUN yarn install --frozen-lockfile

# build resources
FROM base as builder
WORKDIR /app/web
COPY --from=packages /app/web/ .
COPY . .

RUN yarn build


# production stage
FROM base as production

ENV NODE_ENV production
ENV EDITION SELF_HOSTED
ENV DEPLOY_ENV PRODUCTION
ENV CONSOLE_API_URL /
ENV APP_API_URL /
ENV PORT 3000

# set timezone
ENV TZ UTC
RUN ln -s /usr/share/zoneinfo/${TZ} /etc/localtime \
  && echo ${TZ} > /etc/timezone

# global runtime packages
RUN yarn global add pm2 \
  && yarn cache clean

WORKDIR /app/web
COPY --from=builder /app/web/public ./public
COPY --from=builder /app/web/.next/standalone ./
COPY --from=builder /app/web/.next/static ./.next/static


COPY docker/pm2.json ./pm2.json
COPY docker/entrypoint.sh ./entrypoint.sh

ARG COMMIT_SHA
ENV COMMIT_SHA ${COMMIT_SHA}

EXPOSE 3000
ENTRYPOINT ["/bin/sh", "./entrypoint.sh"]

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA routing plus /api proxied to the api service on the compose network.
RUN printf 'server {\n\
  listen 80;\n\
  client_max_body_size 512m;\n\
  location /api/ { proxy_pass http://api:8000; proxy_request_buffering off; proxy_read_timeout 600s; }\n\
  location / { root /usr/share/nginx/html; try_files $uri /index.html; }\n\
}\n' > /etc/nginx/conf.d/default.conf

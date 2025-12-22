# Frontend Dockerfile for Glean Admin Dashboard

# Build stage
FROM node:24-alpine AS builder

WORKDIR /app

# Install pnpm
RUN npm install -g pnpm@10.26.0

# Copy workspace configuration
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/ packages/
COPY apps/admin/ apps/admin/
COPY turbo.json ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Build the admin app
RUN pnpm --filter=@glean/admin build

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=builder /app/apps/admin/dist /usr/share/nginx/html

# Copy nginx configuration
COPY apps/admin/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

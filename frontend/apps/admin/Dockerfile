# Frontend Dockerfile for Glean Admin Dashboard

# Build stage
FROM node:26-alpine AS builder

WORKDIR /app

# Match packageManager in package.json. A mismatch makes pnpm download a
# glibc binary that cannot execute on Alpine (ENOEXEC).
RUN npm install -g pnpm@12.16.1

# Copy workspace configuration
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/ packages/
COPY apps/admin/ apps/admin/
COPY turbo.json ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Build the admin app
RUN pnpm --filter=@glean/admin build

# Production stage (unprivileged non-root nginx listening on 8080)
FROM nginxinc/nginx-unprivileged:alpine

# Copy built files
COPY --from=builder /app/apps/admin/dist /usr/share/nginx/html

# Copy nginx configuration
COPY apps/admin/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]

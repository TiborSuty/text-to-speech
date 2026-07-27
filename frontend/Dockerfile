# Uses a Node image for the Vite React frontend.
FROM node:22-slim

# Sets the working directory used by the frontend container.
WORKDIR /app

# Copies package manifests first so Docker can cache npm installation.
COPY package.json package-lock.json ./

# Installs dependencies exactly as recorded in package-lock.json.
RUN npm ci

# Copies the frontend source into the image.
COPY . .

# Documents the Vite development server port.
EXPOSE 5173

# Runs Vite on all container interfaces so the host can reach it.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

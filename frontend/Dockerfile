FROM node:18-alpine
WORKDIR /frontend
COPY . /frontend
RUN npm install -g serve
CMD ["serve", "-s", ".", "-l", "3000"]

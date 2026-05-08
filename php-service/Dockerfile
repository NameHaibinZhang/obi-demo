FROM php:8.2-cli

RUN apt-get update && apt-get install -y libssl-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pecl install mongodb-1.17.0 \
    && docker-php-ext-enable mongodb \
    && docker-php-ext-install mysqli pdo_mysql

WORKDIR /app
COPY index.php .

EXPOSE 8083
CMD ["php", "-S", "0.0.0.0:8083", "/app/index.php"]
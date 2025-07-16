<p align="center">
	
  <img src="https://dashboard.map-action.com/static/media/logo.ff03b7a9.png" width="100" alt="project-logo">
</p>
<p align="center">
    <h1 align="center">Mapapi</h1>
</p>
<p align="center">
    <em>Comprehensive solution for managing and visualizing environment-related incidents.</em>
</p>
<p align="center">
	<img src="https://img.shields.io/github/license/223MapAction/Model_deploy?style=flat-square&amp;logo=opensourceinitiative&amp;logoColor=white&amp;color=0080ff" alt="License">
	<img src="https://img.shields.io/github/last-commit/223MapAction/Mapapi?style=flat-square&amp;logo=git&amp;logoColor=white&amp;color=0080ff" alt="Last Commit">
	<img src="https://img.shields.io/github/languages/top/223MapAction/Mapapi?style=flat-square&amp;color=0080ff" alt="Top Language">
	<img src="https://img.shields.io/github/languages/count/223MapAction/Mapapi?style=flat-square&amp;color=0080ff" alt="Language Count">
</p>
<p align="center">
		<em>Developed with the software and tools below.</em>
</p>
<p align="center">
	<img src="https://img.shields.io/badge/Django-092E20.svg?style=flat-square&amp;logo=Django&amp;logoColor=white" alt="Django">
	<img src="https://img.shields.io/badge/Postgres-336791.svg?style=flat-square&amp;logo=PostgreSQL&amp;logoColor=white" alt="Postgres">
	<img src="https://img.shields.io/badge/Redis-DC382D.svg?style=flat-square&amp;logo=Redis&amp;logoColor=white" alt="Redis">
	<img src="https://img.shields.io/badge/Celery-37814A.svg?style=flat-square&amp;logo=Celery&amp;logoColor=white" alt="Celery">
	<br>
	<img src="https://img.shields.io/badge/Python-3776AB.svg?style=flat-square&amp;logo=Python&amp;logoColor=white" alt="Python">
	<img src="https://img.shields.io/badge/Docker-2496ED.svg?style=flat-square&amp;logo=Docker&amp;logoColor=white" alt="Docker">
	<img src="https://img.shields.io/badge/GitHub%20Actions-2088FF.svg?style=flat-square&amp;logo=GitHub-Actions&amp;logoColor=white" alt="GitHub Actions">
	<img src="https://img.shields.io/badge/Pytest-0A9EDC.svg?style=flat-square&amp;logo=Pytest&amp;logoColor=white" alt="Pytest">
</p>

## Table of Contents

-   [Overview](#overview)
-   [Technologies](#technologies)
-   [Features](#features)
-   [System Architecture](#system-architecture)
-   [Setup](#setup)
-   [Contribute to the project](#contribute-to-the-project)
-   [Authors](#authors)
-   [Licensing](#licensing)
-   [Developer Documentation](#developer-documentation)
-   [DPG Assessment](#dpg-assessment)

## Overview

Mapapi (Map Action API) is a comprehensive solution that combines a robust API. This project is designed to manage and visualize environment-related incidents efficiently and effectively.

## Technologies

-   **Django**: Used to build the backend for Map Action mobile app and dashboard.
-   **Postgres**: Used to store users data and incidents reported
-   **Celery**: Used as an asynchronous task queue/job
-   **Redis**: Used as a message broker for Celery and for caching.

## Features

-   **API**: Provides endpoints for managing and retrieving data on environment-related incidents.
-   **Asynchronous Task Processing**: Uses Celery and Redis to handle background tasks efficiently.
-   **Database Management**: Utilizes Postgres for robust data storage and querying capabilities.

## System Architecture

![System Architecture Diagram](system_arch.png)

### Setup

#### Prerequisites

-   Ensure you have Docker and Docker Compose installed on your system.

#### Clone the repository

```bash
git clone https://github.com/223MapAction/Mapapi.git
cd Mapapi
```

#### Build and run the containers

-   Use Docker Compose to build and run the services defined in the `_cd_pipeline.yml` file.

```bash
docker-compose -f _cd_pipeline.yml up --build
```

-   This command will build the Docker images and start the containers for the application, including the database, API server, Redis, and other services.

#### Access the application

-   Once the containers are up and running, you can access the application at `http://localhost`.

#### Stopping the services

-   To stop the running services, use:

```bash
docker-compose -f _cd_pipeline.yml down
```

This setup leverages Docker to manage dependencies and services, ensuring a consistent environment across different systems.

## Contribute to the project

Map Action is an open source project. Fell free to fork the source and contribute with your features. Please follow our [contribution guidelines](CONTRIBUTING.md).

## Authors

Our code squad : A7640S, Yugo19 & immerSIR

## Licensing

This project was built under the [GNU Affero General Public License](LICENSE).

## Developer Documentation

For more detailed information, please refer to the [Developer Documentation](https://223mapaction.github.io/Mapapi/).

## DPG Assessment

For a detailed assessment of the project's compliance with the Digital Public Goods Standard, please see the [DIGITAL PUBLIC GOODS STANDARD ASSESSMENT](DPG_ASSESSMENT.md). This document outlines our alignment with sustainable development goals, open licensing, and more.

##### Note

if your system is Linux or MacOS,
you have to add 3 on python
example python3 manage.py runserver

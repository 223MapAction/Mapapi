# Use an official Python runtime as a parent image
FROM python:3.10.13-bookworm

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Run linting with flake8

RUN pip install flake8

# Install coverage and run tests
RUN pip install coverage
RUN coverage run manage.py test
RUN coverage report

# Run Django tests
CMD ["python3", "manage.py", "test"]

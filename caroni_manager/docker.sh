#!/bin/bash
TAG=${TAG:="latest"}

image_names=("caroniwf-wf_server" "caroniwf-django" "caroniwf-sitestub")

for image_name in "${image_names[@]}"; do
    docker build -t $image_name --target $image_name .
    docker tag $image_name ghcr.io/shaunbrady/$image_name:$TAG
    docker push ghcr.io/shaunbrady/$image_name:$TAG
done
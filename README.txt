Overlord Telegram Bot in Docker

Build image and tag with '0.5' and 'latest'

	TAG="0.5" docker buildx bake --load
	
Restart stack with updated images

	docker compose up -d --force-recreate

Restart stack with updated specific image

	docker compose up -d --force-recreate --build overlord


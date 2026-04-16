import redis
import os
import json

redis_client = redis.Redis.from_url(
    "rediss://default:AbmsAAIncDI3Njc4N2VkMzlmN2I0MGJmYWFlODMxNTk3MmQ4ZDM4NXAyNDc1MzI@native-eagle-47532.upstash.io:6379"
)

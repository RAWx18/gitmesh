"""
Deployment Configuration for Cosmos Web Chat Integration

This module provides deployment-specific configuration for different environments,
including Docker, Kubernetes, and cloud deployment settings.
"""

import os
from typing import Dict, Any, List, Optional
from pydantic import BaseSettings, Field
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class DeploymentType(str, Enum):
    """Types of deployment."""
    LOCAL = "local"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    CLOUD = "cloud"


class CloudProvider(str, Enum):
    """Supported cloud providers."""
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    DIGITAL_OCEAN = "digitalocean"


class DeploymentSettings(BaseSettings):
    """Deployment configuration settings."""
    
    # Deployment Type
    deployment_type: DeploymentType = Field(
        default=DeploymentType.LOCAL,
        env="DEPLOYMENT_TYPE"
    )
    
    cloud_provider: Optional[CloudProvider] = Field(
        default=None,
        env="CLOUD_PROVIDER"
    )
    
    # Application Configuration
    app_name: str = Field(default="gitmesh-cosmos-chat", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    app_port: int = Field(default=8000, env="APP_PORT")
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")
    
    # Scaling Configuration
    min_replicas: int = Field(default=1, env="MIN_REPLICAS")
    max_replicas: int = Field(default=10, env="MAX_REPLICAS")
    target_cpu_utilization: int = Field(default=70, env="TARGET_CPU_UTILIZATION")
    target_memory_utilization: int = Field(default=80, env="TARGET_MEMORY_UTILIZATION")
    
    # Resource Limits
    cpu_request: str = Field(default="100m", env="CPU_REQUEST")
    cpu_limit: str = Field(default="500m", env="CPU_LIMIT")
    memory_request: str = Field(default="256Mi", env="MEMORY_REQUEST")
    memory_limit: str = Field(default="512Mi", env="MEMORY_LIMIT")
    
    # Health Check Configuration
    health_check_path: str = Field(default="/health", env="HEALTH_CHECK_PATH")
    readiness_probe_path: str = Field(default="/api/v1/health", env="READINESS_PROBE_PATH")
    liveness_probe_path: str = Field(default="/health", env="LIVENESS_PROBE_PATH")
    
    # Load Balancer Configuration
    load_balancer_enabled: bool = Field(default=True, env="LOAD_BALANCER_ENABLED")
    ssl_enabled: bool = Field(default=True, env="SSL_ENABLED")
    domain_name: Optional[str] = Field(default=None, env="DOMAIN_NAME")
    
    # Database Configuration
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    
    # Security Configuration
    security_context_enabled: bool = Field(default=True, env="SECURITY_CONTEXT_ENABLED")
    run_as_non_root: bool = Field(default=True, env="RUN_AS_NON_ROOT")
    read_only_root_filesystem: bool = Field(default=True, env="READ_ONLY_ROOT_FILESYSTEM")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")
    log_aggregation_enabled: bool = Field(default=True, env="LOG_AGGREGATION_ENABLED")
    
    def get_docker_config(self) -> Dict[str, Any]:
        """Get Docker deployment configuration."""
        return {
            "image": f"{self.app_name}:{self.app_version}",
            "ports": [f"{self.app_port}:8000"],
            "environment": {
                "APP_NAME": self.app_name,
                "APP_VERSION": self.app_version,
                "LOG_LEVEL": self.log_level,
                "LOG_FORMAT": self.log_format,
                "DEPLOYMENT_TYPE": self.deployment_type.value
            },
            "volumes": [
                "./logs:/app/logs",
                "./data:/app/data"
            ],
            "restart": "unless-stopped",
            "healthcheck": {
                "test": f"curl -f http://localhost:8000{self.health_check_path} || exit 1",
                "interval": "30s",
                "timeout": "10s",
                "retries": 3,
                "start_period": "40s"
            },
            "networks": ["gitmesh-network"],
            "depends_on": ["redis", "postgres"]
        }
    
    def get_kubernetes_config(self) -> Dict[str, Any]:
        """Get Kubernetes deployment configuration."""
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": self.app_name,
                "labels": {
                    "app": self.app_name,
                    "version": self.app_version,
                    "component": "cosmos-chat"
                }
            },
            "spec": {
                "replicas": self.min_replicas,
                "selector": {
                    "matchLabels": {
                        "app": self.app_name
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": self.app_name,
                            "version": self.app_version
                        }
                    },
                    "spec": {
                        "containers": [{
                            "name": self.app_name,
                            "image": f"{self.app_name}:{self.app_version}",
                            "ports": [{
                                "containerPort": 8000,
                                "name": "http"
                            }],
                            "env": [
                                {"name": "APP_NAME", "value": self.app_name},
                                {"name": "APP_VERSION", "value": self.app_version},
                                {"name": "LOG_LEVEL", "value": self.log_level},
                                {"name": "DEPLOYMENT_TYPE", "value": self.deployment_type.value}
                            ],
                            "resources": {
                                "requests": {
                                    "cpu": self.cpu_request,
                                    "memory": self.memory_request
                                },
                                "limits": {
                                    "cpu": self.cpu_limit,
                                    "memory": self.memory_limit
                                }
                            },
                            "livenessProbe": {
                                "httpGet": {
                                    "path": self.liveness_probe_path,
                                    "port": 8000
                                },
                                "initialDelaySeconds": 30,
                                "periodSeconds": 10,
                                "timeoutSeconds": 5,
                                "failureThreshold": 3
                            },
                            "readinessProbe": {
                                "httpGet": {
                                    "path": self.readiness_probe_path,
                                    "port": 8000
                                },
                                "initialDelaySeconds": 5,
                                "periodSeconds": 5,
                                "timeoutSeconds": 3,
                                "failureThreshold": 3
                            },
                            "securityContext": {
                                "runAsNonRoot": self.run_as_non_root,
                                "readOnlyRootFilesystem": self.read_only_root_filesystem,
                                "allowPrivilegeEscalation": False,
                                "capabilities": {
                                    "drop": ["ALL"]
                                }
                            } if self.security_context_enabled else {}
                        }],
                        "securityContext": {
                            "runAsUser": 1000,
                            "runAsGroup": 1000,
                            "fsGroup": 1000
                        } if self.security_context_enabled else {}
                    }
                }
            }
        }
    
    def get_service_config(self) -> Dict[str, Any]:
        """Get Kubernetes service configuration."""
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"{self.app_name}-service",
                "labels": {
                    "app": self.app_name
                }
            },
            "spec": {
                "selector": {
                    "app": self.app_name
                },
                "ports": [{
                    "port": 80,
                    "targetPort": 8000,
                    "protocol": "TCP",
                    "name": "http"
                }],
                "type": "LoadBalancer" if self.load_balancer_enabled else "ClusterIP"
            }
        }
    
    def get_hpa_config(self) -> Dict[str, Any]:
        """Get Horizontal Pod Autoscaler configuration."""
        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{self.app_name}-hpa"
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": self.app_name
                },
                "minReplicas": self.min_replicas,
                "maxReplicas": self.max_replicas,
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": self.target_cpu_utilization
                            }
                        }
                    },
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "memory",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": self.target_memory_utilization
                            }
                        }
                    }
                ]
            }
        }
    
    def get_ingress_config(self) -> Dict[str, Any]:
        """Get Ingress configuration."""
        if not self.domain_name:
            return {}
        
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{self.app_name}-ingress",
                "annotations": {
                    "kubernetes.io/ingress.class": "nginx",
                    "cert-manager.io/cluster-issuer": "letsencrypt-prod" if self.ssl_enabled else "",
                    "nginx.ingress.kubernetes.io/ssl-redirect": "true" if self.ssl_enabled else "false"
                }
            },
            "spec": {
                "tls": [{
                    "hosts": [self.domain_name],
                    "secretName": f"{self.app_name}-tls"
                }] if self.ssl_enabled else [],
                "rules": [{
                    "host": self.domain_name,
                    "http": {
                        "paths": [{
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": f"{self.app_name}-service",
                                    "port": {
                                        "number": 80
                                    }
                                }
                            }
                        }]
                    }
                }]
            }
        }
    
    def get_cloud_config(self) -> Dict[str, Any]:
        """Get cloud-specific configuration."""
        if self.cloud_provider == CloudProvider.AWS:
            return {
                "provider": "aws",
                "region": os.getenv("AWS_REGION", "us-east-1"),
                "instance_type": os.getenv("AWS_INSTANCE_TYPE", "t3.medium"),
                "auto_scaling": {
                    "min_size": self.min_replicas,
                    "max_size": self.max_replicas,
                    "desired_capacity": self.min_replicas
                },
                "load_balancer": {
                    "type": "application",
                    "scheme": "internet-facing",
                    "ssl_policy": "ELBSecurityPolicy-TLS-1-2-2017-01"
                }
            }
        elif self.cloud_provider == CloudProvider.GCP:
            return {
                "provider": "gcp",
                "region": os.getenv("GCP_REGION", "us-central1"),
                "machine_type": os.getenv("GCP_MACHINE_TYPE", "e2-medium"),
                "auto_scaling": {
                    "min_replicas": self.min_replicas,
                    "max_replicas": self.max_replicas
                }
            }
        elif self.cloud_provider == CloudProvider.AZURE:
            return {
                "provider": "azure",
                "location": os.getenv("AZURE_LOCATION", "East US"),
                "vm_size": os.getenv("AZURE_VM_SIZE", "Standard_B2s"),
                "auto_scaling": {
                    "min_count": self.min_replicas,
                    "max_count": self.max_replicas
                }
            }
        else:
            return {}
    
    def get_environment_config(self) -> Dict[str, str]:
        """Get environment-specific configuration."""
        base_config = {
            "APP_NAME": self.app_name,
            "APP_VERSION": self.app_version,
            "APP_PORT": str(self.app_port),
            "APP_HOST": self.app_host,
            "LOG_LEVEL": self.log_level,
            "LOG_FORMAT": self.log_format,
            "DEPLOYMENT_TYPE": self.deployment_type.value
        }
        
        if self.database_url:
            base_config["DATABASE_URL"] = self.database_url
        
        if self.redis_url:
            base_config["REDIS_URL"] = self.redis_url
        
        if self.cloud_provider:
            base_config["CLOUD_PROVIDER"] = self.cloud_provider.value
        
        return base_config


# Global deployment settings instance
deployment_settings = DeploymentSettings()


def get_deployment_settings() -> DeploymentSettings:
    """Get the global deployment settings instance."""
    return deployment_settings


def get_deployment_type() -> DeploymentType:
    """Get the current deployment type."""
    return deployment_settings.deployment_type


def is_production_deployment() -> bool:
    """Check if this is a production deployment."""
    return deployment_settings.deployment_type in [DeploymentType.KUBERNETES, DeploymentType.CLOUD]


def get_scaling_config() -> Dict[str, Any]:
    """Get scaling configuration."""
    return {
        "min_replicas": deployment_settings.min_replicas,
        "max_replicas": deployment_settings.max_replicas,
        "target_cpu_utilization": deployment_settings.target_cpu_utilization,
        "target_memory_utilization": deployment_settings.target_memory_utilization
    }
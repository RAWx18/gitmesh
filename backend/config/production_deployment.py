"""
Production Deployment Configuration

This module provides comprehensive production deployment configuration,
including environment setup, feature flag management, and deployment validation.
"""

import os
import json
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
import structlog

from .production import ProductionSettings, FeatureFlag, get_production_settings
from .deployment import DeploymentSettings, get_deployment_settings
from .monitoring import MonitoringSettings, get_monitoring_settings

logger = structlog.get_logger(__name__)


class DeploymentPhase(str, Enum):
    """Deployment phases for gradual rollout."""
    CANARY = "canary"
    BETA = "beta"
    PRODUCTION = "production"


class ValidationLevel(str, Enum):
    """Validation levels for deployment checks."""
    BASIC = "basic"
    COMPREHENSIVE = "comprehensive"
    STRICT = "strict"


@dataclass
class DeploymentConfig:
    """Complete deployment configuration."""
    phase: DeploymentPhase
    environment: str
    version: str
    feature_flags: Dict[str, bool]
    rollout_percentage: int
    validation_level: ValidationLevel
    monitoring_enabled: bool
    security_hardening: bool
    performance_optimizations: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def to_yaml(self) -> str:
        """Convert to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False)


class ProductionDeploymentManager:
    """Manages production deployment configuration and validation."""
    
    def __init__(self):
        """Initialize the deployment manager."""
        self.production_settings = get_production_settings()
        self.deployment_settings = get_deployment_settings()
        self.monitoring_settings = get_monitoring_settings()
        
        # Deployment phases configuration
        self.phase_configs = {
            DeploymentPhase.CANARY: {
                "rollout_percentage": 5,
                "validation_level": ValidationLevel.STRICT,
                "monitoring_enabled": True,
                "feature_flags": {
                    FeatureFlag.COSMOS_CHAT_ENABLED: True,
                    FeatureFlag.COSMOS_CHAT_BETA: True,
                    FeatureFlag.COSMOS_CHAT_FULL: False,
                    FeatureFlag.PERFORMANCE_MONITORING: True,
                    FeatureFlag.SECURITY_HARDENING: True,
                    FeatureFlag.ANALYTICS_TRACKING: True
                }
            },
            DeploymentPhase.BETA: {
                "rollout_percentage": 25,
                "validation_level": ValidationLevel.COMPREHENSIVE,
                "monitoring_enabled": True,
                "feature_flags": {
                    FeatureFlag.COSMOS_CHAT_ENABLED: True,
                    FeatureFlag.COSMOS_CHAT_BETA: True,
                    FeatureFlag.COSMOS_CHAT_FULL: False,
                    FeatureFlag.PERFORMANCE_MONITORING: True,
                    FeatureFlag.SECURITY_HARDENING: True,
                    FeatureFlag.ANALYTICS_TRACKING: True
                }
            },
            DeploymentPhase.PRODUCTION: {
                "rollout_percentage": 100,
                "validation_level": ValidationLevel.BASIC,
                "monitoring_enabled": True,
                "feature_flags": {
                    FeatureFlag.COSMOS_CHAT_ENABLED: True,
                    FeatureFlag.COSMOS_CHAT_BETA: False,
                    FeatureFlag.COSMOS_CHAT_FULL: True,
                    FeatureFlag.PERFORMANCE_MONITORING: True,
                    FeatureFlag.SECURITY_HARDENING: True,
                    FeatureFlag.ANALYTICS_TRACKING: True
                }
            }
        }
    
    def create_deployment_config(
        self,
        phase: DeploymentPhase,
        version: str,
        custom_flags: Optional[Dict[FeatureFlag, bool]] = None
    ) -> DeploymentConfig:
        """Create deployment configuration for a specific phase."""
        try:
            phase_config = self.phase_configs[phase]
            
            # Start with phase defaults
            feature_flags = phase_config["feature_flags"].copy()
            
            # Apply custom flags if provided
            if custom_flags:
                for flag, enabled in custom_flags.items():
                    feature_flags[flag] = enabled
            
            # Convert enum keys to strings for serialization
            feature_flags_str = {flag.value: enabled for flag, enabled in feature_flags.items()}
            
            config = DeploymentConfig(
                phase=phase,
                environment=self.production_settings.environment.value,
                version=version,
                feature_flags=feature_flags_str,
                rollout_percentage=phase_config["rollout_percentage"],
                validation_level=phase_config["validation_level"],
                monitoring_enabled=phase_config["monitoring_enabled"],
                security_hardening=self.production_settings.security_hardening_enabled,
                performance_optimizations=True
            )
            
            logger.info(f"Created deployment config for {phase.value} phase", config=config.to_dict())
            return config
            
        except Exception as e:
            logger.error(f"Error creating deployment config: {e}")
            raise
    
    def validate_deployment_config(self, config: DeploymentConfig) -> Dict[str, Any]:
        """Validate deployment configuration."""
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "checks": {}
        }
        
        try:
            # Basic validation
            validation_results["checks"]["basic"] = self._validate_basic_config(config)
            
            # Environment-specific validation
            if config.validation_level in [ValidationLevel.COMPREHENSIVE, ValidationLevel.STRICT]:
                validation_results["checks"]["environment"] = self._validate_environment_config(config)
            
            # Security validation
            if config.validation_level == ValidationLevel.STRICT:
                validation_results["checks"]["security"] = self._validate_security_config(config)
            
            # Feature flag validation
            validation_results["checks"]["feature_flags"] = self._validate_feature_flags(config)
            
            # Resource validation
            validation_results["checks"]["resources"] = self._validate_resource_config(config)
            
            # Collect errors and warnings
            for check_name, check_result in validation_results["checks"].items():
                if check_result.get("errors"):
                    validation_results["errors"].extend(check_result["errors"])
                if check_result.get("warnings"):
                    validation_results["warnings"].extend(check_result["warnings"])
            
            validation_results["valid"] = len(validation_results["errors"]) == 0
            
            logger.info(
                f"Deployment validation completed",
                valid=validation_results["valid"],
                errors=len(validation_results["errors"]),
                warnings=len(validation_results["warnings"])
            )
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating deployment config: {e}")
            validation_results["valid"] = False
            validation_results["errors"].append(f"Validation error: {e}")
            return validation_results
    
    def _validate_basic_config(self, config: DeploymentConfig) -> Dict[str, Any]:
        """Validate basic configuration requirements."""
        result = {"errors": [], "warnings": []}
        
        # Check required fields
        if not config.version:
            result["errors"].append("Version is required")
        
        if config.rollout_percentage < 0 or config.rollout_percentage > 100:
            result["errors"].append("Rollout percentage must be between 0 and 100")
        
        # Check version format
        if config.version and not config.version.replace(".", "").replace("-", "").isalnum():
            result["warnings"].append("Version format may not be standard")
        
        return result
    
    def _validate_environment_config(self, config: DeploymentConfig) -> Dict[str, Any]:
        """Validate environment-specific configuration."""
        result = {"errors": [], "warnings": []}
        
        # Check environment variables
        required_env_vars = [
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY",
            "JWT_SECRET"
        ]
        
        for var in required_env_vars:
            if not os.getenv(var):
                result["errors"].append(f"Required environment variable {var} is not set")
        
        # Check AI API keys
        ai_keys = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
        if not any(os.getenv(key) for key in ai_keys):
            result["errors"].append("At least one AI API key must be configured")
        
        # Check Redis configuration
        redis_url = os.getenv("REDIS_URL")
        if redis_url and "localhost" in redis_url and config.environment == "production":
            result["warnings"].append("Using localhost Redis in production environment")
        
        return result
    
    def _validate_security_config(self, config: DeploymentConfig) -> Dict[str, Any]:
        """Validate security configuration."""
        result = {"errors": [], "warnings": []}
        
        # Check secret key strength
        secret_key = os.getenv("SECRET_KEY", "")
        if len(secret_key) < 32:
            result["errors"].append("SECRET_KEY must be at least 32 characters long")
        
        # Check JWT secret
        jwt_secret = os.getenv("JWT_SECRET", "")
        if len(jwt_secret) < 32:
            result["errors"].append("JWT_SECRET must be at least 32 characters long")
        
        # Check if security hardening is enabled
        if not config.security_hardening:
            result["warnings"].append("Security hardening is disabled")
        
        # Check HTTPS configuration
        if config.environment == "production":
            frontend_url = os.getenv("FRONTEND_URL", "")
            if frontend_url and not frontend_url.startswith("https://"):
                result["warnings"].append("HTTPS should be used in production")
        
        return result
    
    def _validate_feature_flags(self, config: DeploymentConfig) -> Dict[str, Any]:
        """Validate feature flag configuration."""
        result = {"errors": [], "warnings": []}
        
        # Check for conflicting flags
        flags = config.feature_flags
        
        if flags.get("cosmos_chat_enabled") and not flags.get("redis_repo_manager"):
            result["errors"].append("Cosmos chat requires Redis repository manager")
        
        if flags.get("real_time_chat") and not flags.get("cosmos_chat_enabled"):
            result["warnings"].append("Real-time chat enabled but Cosmos chat is disabled")
        
        if flags.get("analytics_tracking") and not flags.get("performance_monitoring"):
            result["warnings"].append("Analytics tracking enabled but performance monitoring is disabled")
        
        # Check phase-specific requirements
        if config.phase == DeploymentPhase.PRODUCTION:
            if flags.get("cosmos_chat_beta"):
                result["warnings"].append("Beta features should not be enabled in production")
        
        return result
    
    def _validate_resource_config(self, config: DeploymentConfig) -> Dict[str, Any]:
        """Validate resource configuration."""
        result = {"errors": [], "warnings": []}
        
        # Check deployment settings
        if self.deployment_settings.min_replicas < 2 and config.environment == "production":
            result["warnings"].append("Consider using at least 2 replicas in production")
        
        if self.deployment_settings.max_replicas < 5 and config.rollout_percentage > 50:
            result["warnings"].append("Consider increasing max replicas for high rollout percentage")
        
        # Check resource limits
        cpu_limit = self.deployment_settings.cpu_limit
        memory_limit = self.deployment_settings.memory_limit
        
        if cpu_limit == "500m" and config.rollout_percentage > 25:
            result["warnings"].append("Consider increasing CPU limits for higher rollout")
        
        if memory_limit == "512Mi" and config.rollout_percentage > 25:
            result["warnings"].append("Consider increasing memory limits for higher rollout")
        
        return result
    
    def generate_kubernetes_manifests(self, config: DeploymentConfig) -> Dict[str, str]:
        """Generate Kubernetes manifests for deployment."""
        try:
            manifests = {}
            
            # Generate ConfigMap
            manifests["configmap.yaml"] = self._generate_configmap(config)
            
            # Generate Deployment
            manifests["deployment.yaml"] = self._generate_deployment(config)
            
            # Generate Service
            manifests["service.yaml"] = self._generate_service(config)
            
            # Generate HPA
            manifests["hpa.yaml"] = self._generate_hpa(config)
            
            # Generate Ingress if needed
            if self.deployment_settings.domain_name:
                manifests["ingress.yaml"] = self._generate_ingress(config)
            
            logger.info(f"Generated {len(manifests)} Kubernetes manifests")
            return manifests
            
        except Exception as e:
            logger.error(f"Error generating Kubernetes manifests: {e}")
            raise
    
    def _generate_configmap(self, config: DeploymentConfig) -> str:
        """Generate ConfigMap manifest."""
        configmap_data = {
            "APP_NAME": "gitmesh-cosmos-chat",
            "APP_VERSION": config.version,
            "DEPLOYMENT_ENVIRONMENT": config.environment,
            "DEPLOYMENT_TYPE": "kubernetes",
            "COSMOS_CHAT_ROLLOUT_PERCENTAGE": str(config.rollout_percentage),
            "MONITORING_ENABLED": str(config.monitoring_enabled).lower(),
            "SECURITY_HARDENING_ENABLED": str(config.security_hardening).lower()
        }
        
        # Add feature flags
        for flag, enabled in config.feature_flags.items():
            configmap_data[f"FEATURE_{flag.upper()}"] = str(enabled).lower()
        
        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "cosmos-chat-config",
                "namespace": "cosmos-chat",
                "labels": {
                    "app": "gitmesh-cosmos-chat",
                    "version": config.version,
                    "phase": config.phase.value
                }
            },
            "data": configmap_data
        }
        
        return yaml.dump(configmap, default_flow_style=False)
    
    def _generate_deployment(self, config: DeploymentConfig) -> str:
        """Generate Deployment manifest."""
        # Calculate replicas based on rollout percentage
        base_replicas = self.deployment_settings.min_replicas
        max_replicas = self.deployment_settings.max_replicas
        rollout_replicas = max(1, int(base_replicas * (config.rollout_percentage / 100)))
        replicas = min(rollout_replicas, max_replicas)
        
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "cosmos-chat-app",
                "namespace": "cosmos-chat",
                "labels": {
                    "app": "gitmesh-cosmos-chat",
                    "version": config.version,
                    "phase": config.phase.value
                }
            },
            "spec": {
                "replicas": replicas,
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {
                        "maxSurge": 1,
                        "maxUnavailable": 0
                    }
                },
                "selector": {
                    "matchLabels": {
                        "app": "gitmesh-cosmos-chat"
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "gitmesh-cosmos-chat",
                            "version": config.version,
                            "phase": config.phase.value
                        },
                        "annotations": {
                            "prometheus.io/scrape": "true" if config.monitoring_enabled else "false",
                            "prometheus.io/port": "8000",
                            "prometheus.io/path": "/api/v1/cosmos/health/metrics"
                        }
                    },
                    "spec": {
                        "serviceAccountName": "cosmos-chat-service-account",
                        "securityContext": {
                            "runAsUser": 1000,
                            "runAsGroup": 1000,
                            "fsGroup": 1000,
                            "runAsNonRoot": True
                        } if config.security_hardening else {},
                        "containers": [{
                            "name": "cosmos-chat",
                            "image": f"gitmesh-cosmos-chat:{config.version}",
                            "imagePullPolicy": "Always",
                            "ports": [{
                                "containerPort": 8000,
                                "name": "http",
                                "protocol": "TCP"
                            }],
                            "envFrom": [{
                                "configMapRef": {
                                    "name": "cosmos-chat-config"
                                }
                            }, {
                                "secretRef": {
                                    "name": "cosmos-chat-secrets"
                                }
                            }],
                            "resources": {
                                "requests": {
                                    "cpu": self.deployment_settings.cpu_request,
                                    "memory": self.deployment_settings.memory_request
                                },
                                "limits": {
                                    "cpu": self.deployment_settings.cpu_limit,
                                    "memory": self.deployment_settings.memory_limit
                                }
                            },
                            "livenessProbe": {
                                "httpGet": {
                                    "path": "/api/v1/cosmos/health/liveness",
                                    "port": 8000
                                },
                                "initialDelaySeconds": 30,
                                "periodSeconds": 10,
                                "timeoutSeconds": 5,
                                "failureThreshold": 3
                            },
                            "readinessProbe": {
                                "httpGet": {
                                    "path": "/api/v1/cosmos/health/readiness",
                                    "port": 8000
                                },
                                "initialDelaySeconds": 5,
                                "periodSeconds": 5,
                                "timeoutSeconds": 3,
                                "failureThreshold": 3
                            },
                            "securityContext": {
                                "runAsNonRoot": True,
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "readOnlyRootFilesystem": True,
                                "allowPrivilegeEscalation": False,
                                "capabilities": {
                                    "drop": ["ALL"]
                                }
                            } if config.security_hardening else {}
                        }]
                    }
                }
            }
        }
        
        return yaml.dump(deployment, default_flow_style=False)
    
    def _generate_service(self, config: DeploymentConfig) -> str:
        """Generate Service manifest."""
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "cosmos-chat-service",
                "namespace": "cosmos-chat",
                "labels": {
                    "app": "gitmesh-cosmos-chat",
                    "version": config.version
                }
            },
            "spec": {
                "type": "LoadBalancer",
                "selector": {
                    "app": "gitmesh-cosmos-chat"
                },
                "ports": [{
                    "name": "http",
                    "port": 80,
                    "targetPort": 8000,
                    "protocol": "TCP"
                }]
            }
        }
        
        return yaml.dump(service, default_flow_style=False)
    
    def _generate_hpa(self, config: DeploymentConfig) -> str:
        """Generate HPA manifest."""
        # Adjust HPA based on rollout percentage
        min_replicas = max(1, int(self.deployment_settings.min_replicas * (config.rollout_percentage / 100)))
        max_replicas = int(self.deployment_settings.max_replicas * (config.rollout_percentage / 100))
        
        hpa = {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": "cosmos-chat-hpa",
                "namespace": "cosmos-chat",
                "labels": {
                    "app": "gitmesh-cosmos-chat"
                }
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": "cosmos-chat-app"
                },
                "minReplicas": min_replicas,
                "maxReplicas": max_replicas,
                "metrics": [{
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": self.deployment_settings.target_cpu_utilization
                        }
                    }
                }, {
                    "type": "Resource",
                    "resource": {
                        "name": "memory",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": self.deployment_settings.target_memory_utilization
                        }
                    }
                }]
            }
        }
        
        return yaml.dump(hpa, default_flow_style=False)
    
    def _generate_ingress(self, config: DeploymentConfig) -> str:
        """Generate Ingress manifest."""
        ingress = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": "cosmos-chat-ingress",
                "namespace": "cosmos-chat",
                "annotations": {
                    "kubernetes.io/ingress.class": "nginx",
                    "cert-manager.io/cluster-issuer": "letsencrypt-prod",
                    "nginx.ingress.kubernetes.io/ssl-redirect": "true"
                }
            },
            "spec": {
                "tls": [{
                    "hosts": [self.deployment_settings.domain_name],
                    "secretName": "cosmos-chat-tls"
                }],
                "rules": [{
                    "host": self.deployment_settings.domain_name,
                    "http": {
                        "paths": [{
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": "cosmos-chat-service",
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
        
        return yaml.dump(ingress, default_flow_style=False)
    
    def save_deployment_artifacts(self, config: DeploymentConfig, output_dir: str = "deployment"):
        """Save deployment configuration and manifests to files."""
        try:
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)
            
            # Save deployment config
            config_file = output_path / f"deployment-config-{config.phase.value}.json"
            with open(config_file, "w") as f:
                f.write(config.to_json())
            
            # Save Kubernetes manifests
            manifests = self.generate_kubernetes_manifests(config)
            for filename, content in manifests.items():
                manifest_file = output_path / f"{config.phase.value}-{filename}"
                with open(manifest_file, "w") as f:
                    f.write(content)
            
            logger.info(f"Deployment artifacts saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error saving deployment artifacts: {e}")
            raise


# Global deployment manager instance
deployment_manager = ProductionDeploymentManager()


def get_deployment_manager() -> ProductionDeploymentManager:
    """Get the global deployment manager instance."""
    return deployment_manager


def create_deployment_config(
    phase: DeploymentPhase,
    version: str,
    custom_flags: Optional[Dict[FeatureFlag, bool]] = None
) -> DeploymentConfig:
    """Create deployment configuration for a specific phase."""
    return deployment_manager.create_deployment_config(phase, version, custom_flags)


def validate_deployment(config: DeploymentConfig) -> Dict[str, Any]:
    """Validate deployment configuration."""
    return deployment_manager.validate_deployment_config(config)
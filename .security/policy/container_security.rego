package main

import rego.v1

digest_pinned(image) if regex.match(`^[a-z0-9][a-z0-9._/-]*@sha256:[a-f0-9]{64}$`, image)

images contains image if {
  some name
  image := input.services[name].image
}

images contains image if {
  some container in input.spec.template.spec.containers
  image := container.image
}

images contains image if {
  image := input.image.repository
}

deny contains sprintf("mutable image reference: %s", [image]) if {
  some image in images
  not startswith(image, "$")
  not digest_pinned(image)
}

deny contains "privileged containers are prohibited" if {
  some container in input.spec.template.spec.containers
  container.securityContext.privileged == true
}

deny contains "host networking is prohibited" if input.spec.hostNetwork == true
deny contains "host PID is prohibited" if input.spec.hostPID == true
deny contains "host IPC is prohibited" if input.spec.hostIPC == true

deny contains sprintf("compose service %s is privileged", [name]) if {
  input.services[name].privileged == true
}

deny contains sprintf("compose service %s uses host networking", [name]) if {
  input.services[name].network_mode == "host"
}

deny contains sprintf("compose service %s must use a read-only root filesystem", [name]) if {
  input.services[name].image
  not input.services[name].read_only == true
}

deny contains sprintf("compose service %s must run as a non-root user", [name]) if {
  input.services[name].image
  not input.services[name].user
}

deny contains sprintf("compose service %s must drop all capabilities", [name]) if {
  input.services[name].image
  not "ALL" in input.services[name].cap_drop
}

deny contains sprintf("compose service %s must enforce no-new-privileges", [name]) if {
  input.services[name].image
  not "no-new-privileges:true" in input.services[name].security_opt
}

deny contains sprintf("compose service %s exposes a public host port", [name]) if {
  some port in input.services[name].ports
  regex.match(`^(?:0\.0\.0\.0:|[0-9]+:)`, sprintf("%v", [port]))
}

deny contains "Kubernetes containers must run as non-root" if {
  some container in input.spec.template.spec.containers
  not container.securityContext.runAsNonRoot == true
}

deny contains "Kubernetes containers must use read-only root filesystems" if {
  some container in input.spec.template.spec.containers
  not container.securityContext.readOnlyRootFilesystem == true
}

deny contains "Kubernetes containers must drop all capabilities" if {
  some container in input.spec.template.spec.containers
  not "ALL" in container.securityContext.capabilities.drop
}

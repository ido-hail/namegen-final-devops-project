# Runtime validation evidence

Captured read-only on `2026-08-19T18:54:13Z` after GitHub Actions deployed commit `445d3ce07ee00335d30c586db32830c609eea271`.

Sensitive values, the AWS Account ID, generated endpoints, and resource IDs are intentionally omitted.

```text
Application Deployment
namegen   desired=2   ready=2   updated=2   available=2

MongoDB StatefulSet
mongodb   desired=1   ready=1   current=1   image=mongo:3.6

Persistent storage
mongodb-data-mongodb-0   Bound   1Gi   namegen-gp3
CSI driver: ebs.csi.eks.amazonaws.com
EBS: type=gp3   size=1GiB   encrypted=true   state=in-use

Public Service
namegen   type=LoadBalancer   class=eks.amazonaws.com/nlb   port=80

Monitoring
release: namegen-monitoring
chart: kube-prometheus-stack-87.21.0
status: deployed
dashboard UID: namegen-runtime
dashboard panels: 4
services: internal ClusterIP
live NameGen readiness metric series: 3
```

The matching GitHub Actions run completed both `Test application` and `Build and deploy immutable image`: [workflow run 32289057576](https://github.com/ido-hail/namegen-final-devops-project/actions/runs/32289057576).

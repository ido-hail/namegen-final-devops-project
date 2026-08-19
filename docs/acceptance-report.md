# Final acceptance report

Audited on `2026-08-19` against deployed application commit
`555c6b737139d864e4a845d522963ec6c06ae906`.

This report maps the repository working agreement, the approved project
decisions, and the implemented lifecycle to concrete evidence. No separate
assignment specification is stored in the repository, so no additional
criteria were inferred beyond those sources.

| Acceptance area | Verified evidence | Status |
| --- | --- | --- |
| Reproducible infrastructure | Terraform validation passed for the bootstrap and runtime configurations. A saved read-only plan reported no infrastructure drift. | Pass |
| Terraform state | The S3 bucket is versioned, encrypted with AES256, and blocks all public access. Launch creates it; teardown deletes every version and then the bucket, after the runtime audit. | Pass |
| EKS runtime | EKS Auto Mode is active. The NameGen Deployment has exactly two desired, updated, available, and Ready replicas on the expected 40-character Git SHA. | Pass |
| MongoDB and storage | MongoDB `3.6` has exactly one Ready replica. Its PVC is Bound at `1Gi` through `namegen-gp3`, backed by encrypted `gp3` EBS. | Pass |
| Persistence | The persistence workflow recreated only `mongodb-0`, observed a new Pod UID, retained the same PersistentVolume, and read the saved marker afterward. The marker remained readable during the final audit. | Pass |
| Public application | AWS reports an active internet-facing Network Load Balancer. The UI, connection, random-name, save, and list flows passed; the connection response exposes only host, port, and database name. | Pass |
| Monitoring | `kube-prometheus-stack-87.21.0` is deployed. Grafana, Prometheus, and exporters are Ready; Services remain `ClusterIP`; the four-panel dashboard is loaded; Prometheus returned three live NameGen readiness series. | Pass |
| Immutable delivery | GitHub Actions authenticated through the immutable repository OIDC subject, tested the application, built `linux/amd64`, pushed a full-SHA immutable tag, deployed it, and validated the rollout. | Pass |
| Container security | The application image runs as the non-root `node` user. `npm audit --omit=dev` reported zero vulnerabilities. ECR basic scanning completed successfully with no findings after moving the runtime base to Alpine. | Pass |
| Least privilege | The GitHub role is limited to ECR image delivery and EKS discovery. Its Kubernetes group can patch the NameGen Deployment but cannot read Secrets or delete Pods. No static AWS credentials are used. | Pass |
| Network and portability constraints | Only the NameGen NLB is public. MongoDB and monitoring are internal. No NAT Gateway, Elastic IP, committed Account ID, generated endpoint, Kubernetes Secret, credential URI, or `latest` image is present. | Pass |
| CI/CD evidence | Both jobs in [workflow run 32292889386](https://github.com/ido-hail/namegen-final-devops-project/actions/runs/32292889386) completed successfully for the deployed commit. | Pass |
| Complete teardown | A non-mutating preview found 26 managed state addresses and produced exactly 23 delete-only resource changes. Kubernetes/NLB/EBS cleanup precedes Terraform; the versioned state bucket is deleted last. | Pass |
| Documentation and evidence | The README covers architecture, deployment, access, CI/CD, validation, and complete removal. Sanitized UI, CI, Grafana, and runtime evidence is stored under `docs/evidence/`. | Pass |

## Residual decisions and risks

- The environment is still live and billable. No teardown was executed during
  this audit; it requires a separately approved destructive segment.
- MongoDB `3.6` is a legacy runtime, retained because it is an explicit project
  compatibility requirement. It should not be treated as a recommended version
  for a new production system.
- The EKS API has public and private access enabled so GitHub-hosted runners can
  deploy. API authentication uses AWS/EKS, and the GitHub principal is restricted
  by IAM and Kubernetes RBAC.
- The teardown path has been validated by mocks and a live saved-plan preview,
  but its destructive Apply path intentionally remains unexecuted until the
  evidence is accepted and removal is explicitly approved.

## Acceptance conclusion

The implemented system satisfies the agreed final-project criteria and is ready
for submission or demonstration. The only remaining lifecycle action is the
explicit, irreversible teardown after the evidence has been accepted.

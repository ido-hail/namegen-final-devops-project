# NameGen DevOps Working Agreement

## Objective

Complete, validate, document, and safely tear down the NameGen deployment on
Amazon EKS Auto Mode. Work in bounded segments and finish each segment with
evidence, a Git audit, and a concise handoff.

## Autonomy boundaries

- Within an approved segment, inspect files and runtime state, edit in-scope
  files, run non-destructive validation, fix incidental defects, and rerun the
  relevant checks without pausing for routine approval.
- Ask before materially changing architecture, cost, IAM scope, credential or
  Secret handling, or the agreed acceptance criteria.
- Ask before creating infrastructure outside an approved deployment segment.
- Never delete Terraform state, EKS, VPC, EBS, PVCs, PersistentVolumes, or
  application data unless the user explicitly approves the teardown segment.
- Commit and push only when the active segment authorizes publication and all
  relevant validation passes.

## Security and portability invariants

- Never commit credentials, Kubernetes Secrets, literal passwords, AWS access
  keys, the AWS Account ID, generated endpoints, or MongoDB credential URIs.
- Use full 40-character Git SHA image tags. Never deploy `latest`.
- Keep the application container non-root and target `linux/amd64`.
- Keep monitoring internal. Only the NameGen NLB is internet-facing.
- Do not add NAT Gateways or Elastic IPs.
- Preserve the encrypted `gp3` MongoDB volume and the 1 GiB PVC requirement.
- Redact Secret input and authentication tokens from command output.

## Live-runtime safeguards

- Before runtime work, inspect Git, Terraform state, Kubernetes workloads, ECR,
  and Helm release state. Do not assume the environment is clean.
- Do not rerun the full `scripts/launch.py --apply` workflow against an existing
  deployment. Its clean-deployment path expects empty runtime state and creates
  fresh MongoDB credentials.
- When MongoDB already has persistent data, never replace
  `mongodb-credentials` unless credential rotation and database migration are
  explicitly approved together.
- Recover an existing deployment incrementally: build and push the current Git
  SHA image, update only the intended manifests, then validate each layer.
- Persistence validation may recreate only the `mongodb-0` Pod. It must retain
  the same PVC and PersistentVolume.
- Teardown must use `scripts/terminate.py` only after explicit approval and must
  preserve or remove the state bucket according to the final documented policy.

## Required validation

Run the checks relevant to changed files and the active segment. The complete
local baseline is:

```sh
node --check server.js
PYTHONPYCACHEPREFIX=/private/tmp/namegen-pycache python3 -m py_compile scripts/launch.py scripts/terminate.py
PYTHONPYCACHEPREFIX=/private/tmp/namegen-pycache python3 -m unittest discover -s tests -p 'test_*.py'
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform validate
terraform -chdir=terraform/bootstrap fmt -check -recursive
terraform -chdir=terraform/bootstrap validate
kubectl kustomize k8s >/dev/null
kubectl kustomize monitoring >/dev/null
helm template namegen-monitoring prometheus-community/kube-prometheus-stack --version 87.21.0 --namespace monitoring --values monitoring/values.yaml >/dev/null
git diff --check
```

For a live deployment, also verify:

- exactly two Ready NameGen replicas running the expected Git SHA image;
- exactly one Ready MongoDB 3.6 replica;
- a Bound 1 GiB PVC backed by encrypted `gp3` EBS;
- an active internet-facing Network Load Balancer;
- successful UI, connection, random-name, save, and list requests;
- data survival after recreation of only the MongoDB Pod;
- the pinned monitoring chart, four-panel dashboard, internal Services, and a
  live NameGen Prometheus readiness series.

## Git discipline

- Preserve unrelated user changes and inspect the working tree before editing.
- Keep commits scoped and use the repository's conventional prefixes such as
  `fix:`, `build:`, `infra:`, `k8s:`, `monitoring:`, and `docs:`.
- Before publication, run `git diff --check`, inspect the staged diff, scan it
  for credential or identity material, and confirm local and remote `main`
  match after the push.

## Segment handoff

At the end of every segment, report:

1. the outcome and evidence;
2. files, commits, and external resources changed;
3. decisions, deviations, risks, and remaining cost-bearing resources;
4. what remains in the project plan;
5. whether the autonomous workflow reduced manual handoffs without weakening
   review, security, or validation.

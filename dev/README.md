# LoL Optimizer deployment

## Requirements

- Active Oracle Cloud Account
- Credits available
- Administrative permissions

## Download

Open OCI Console, and click Cloud Shell.

```
git clone --branch livelabs https://github.com/jasperan/f1-telemetry-oracle.git
```

Change to `f1-telemetry-oracle` directory:
```
cd f1-telemetry-oracle/
```

## Set up

From this directory `./dev`.
```
cd dev/
```

```
cp terraform/terraform.tfvars.template terraform/terraform.tfvars
```

Get details for the `terraform.tfvars` file:
- Tenancy:
  ```
  echo $OCI_TENANCY
  ```
- Compartment (root by default):
  ```
  echo $OCI_TENANCY
  ```
  > If you need a specific compartment, get the OCID by name with:
  > ```
  > oci iam compartment list --all --compartment-id-in-subtree true --name COMPARTMENT_NAME --query "data[].id"
  > ```
- SSH Public Key:
  ```
  cat ~/.ssh/id_rsa.pub
  ```


Edit the values with `vim` or `nano` with your tenancy, compartment, ssh public key and Riot API key:
```
vim terraform/terraform.tfvars
```

## Deploy

```
./start.sh
```

> If there are permission errors with **start.sh**, make sure to change permissions appropriately before trying to execute again:
  ```
  chmod 700 start.sh
  ```


The output will be an `ssh` command to connect with the machine.

> Re-run the `start.sh` in case of failure

## Test

After ssh into the machine, run the check app.

```
python3 src/check.py
```

All checks should indicate `OK`. If any `FAIL`, review the setup and make sure `terraform.tfvars` are valid.

### Destroy

```
./stop.sh
```
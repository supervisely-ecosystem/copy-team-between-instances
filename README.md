# Copy team between instances

# Introduction

Import Supervisely Team from one instance to another. All selected team members, workspaces, and team files will be imported.

App can be used **only by master user of the both instances**: current (where you run the app) and the one you want to import from.

<details>
<summary open>App screenshot</summary>
<br>

<div align="center">
  <img src="https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/da4d02b8-900f-4b46-b980-69df54ce18cd"/>
</div>

</details>

# How to Use

## Step 1. Connect to instance you want to import from

![connect](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/a37bbe9b-0a7b-4791-9f92-b6609f03fbde)

1. Provide server address

Copy server address from your browser address bar.

![server-address](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/cf4e99d2-7722-43b9-88d1-8b010409a6c2)

2. Provide API token. You can find it in your profile settings on the instance you want to import from.

Open instance you want to import from in browser and login as master user. Then go to your profile settings.

![profile-settings](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/18cd741b-db37-42d9-ba24-1cc230d41733)

Open API Token tab and copy your token to the app.

![profile-token](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/6743f9e8-a71c-4214-9c2f-cfa0247c357f)

3. Press "Connect" button.

![connect-success](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/238335f4-a00f-44aa-b405-39fd3b22e732)

## Step 2. Select team to import. Press on the "Select" button in the table of the team you want to import.

![team-table](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/491ccfeb-0d11-4e5b-956f-2d4156b7fa87)

## Step 3. Select Entities to import

There are three sections in the app each of them allows you to select and configure specific items that you want to import:

1. Workspaces
2. Team Members
3. Team Files

![select-entities](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/175f2190-7a6c-4500-8c12-b0c99d89863e)

### 1. Workspaces

In this section you can select which workspaces you want to import.
If you want to import all workspaces, check "Import all workspaces" checkbox, otherwise you can manually select specific projects in workspaces that you want to import.

![entities-ws](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/d88b1d2e-c104-4d20-8574-c9a7680e719a)

If the team you want to import already exists on the current instance, you might find projects in selector that are marked as disabled. It means that these project already exists in selected workspace and these projects will not be imported unless "Remove and reupload projects that already exists" option is selected.

![ws-projects-exists](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/79d0c981-e6d1-448a-ac61-b566c687f4d6)

**Workspace import options**

There are a few options to select from when importing workspaces:

1. Data collision - what to do if project with the same name already exists in the workspace you want to import to.
    - Skip projects that already exists - ignore projects that already exists on the current instance.
    - Remove and reupload projects that already exists - remove project from current instance and reupload it from the instance you want to import from.

2. Data transfer - select how to import data from another instance based on original upload method.
    - Copy data from instance to instance by reuploading (Slow) - completely reupload all data from another instance. Slow, but safe option.
    - Copy data by links, if possible (Fast) - if your data is linked to cloud storage, these links will be used when transferring data. If those links don't exists anymore, data will not be validated, which can result in data loss. If data is not available by link, it will be reuploaded using default method. Fast but not safe option.

If you want to copy data by links from cloud storage, but you migrated your data to another cloud storage you can use "Change transfer links for items" option. This option requires you to connect to cloud storage you want to use for data transfer.

![change-link-connect](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/4a1aadc8-400b-4a63-950b-d143b3297ef6)

Select provider, enter the bucket name and press "Connect" button. If you have successfully connected old cloud storage links will be replaced with new ones using new provider and bucket name.

![change-link-connect-success](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/b19cc201-f86a-4037-998b-4fa0c588933a)

For example you migrated your data from GCS to AWS **keeping the same folder structure** for your data. You can use this option to replace old GCS links with new AWS links.

```text
 'gcs://my-bucket/data/my_project/image_01.jpg' -> 's3://new-bucket/data/my_project/image_01.jpg'
```

Please notice that only provider and bucket name have changed, but folder structure for image is the same.

### 2. Team Members

In this section you can select which team members you want to import.

You can see the list of team members and their roles on the instance you want to import from. Manually select specific team members that you want to import.

If you see that some users are marked as disabled, it means that team that you want to import already exists on the current instance, and these users are already in this team and exists and they will not be imported. In case their roles are different, you can change them to match roles on the instance you are importing from.

![entities-users](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/7f33697f-5407-4e58-a42e-e0400aa64d05)

If users you want to import are completely new to the current instance, they will be created with the role "annotator" and you need to specify default password for them. Don't forget to notify them about their new password.

### 3. Team Files

In this section you can select which team files you want to import. Simply select files that you want to import in the file selector, or check all files by clicking on checkbox in the top left corner of file selector widget.

![entities-files](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/08aad5b2-2d07-482a-acb8-e838fd07ba2d)

## Step 4. Start import

Press "Start Import" button and wait for the app to transfer data between instances, once finished you will see the following message: "Data have been successfully imported.".
You can finish the app or select another team to import.

![import-success](https://github.com/supervisely-ecosystem/copy-team-between-instances/assets/48913536/b88d11c3-61b9-4dbf-8cc1-1bde52fc64f7)

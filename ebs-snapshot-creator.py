import boto3
import collections
from datetime import datetime

ec = boto3.client('ec2')

def lambda_handler(event, context):
    regions = [context.invoked_function_arn.split(':')[3]]
    if 'regions' in event:
        regions = event['regions']

    print("AWS snapshot backups stated at %s...\n" % datetime.now())
    for region in regions:
        print("Region: %s" % region)
        create_region_snapshots(region)
    print("\nAWS snapshot backups completed at %s\n" % datetime.now())

# create snapshot for region
def create_region_snapshots(region):
    reservations = ec.describe_instances(
        Filters=[
            { 'Name': 'tag:Backup', 'Values': ['Yes'] },
        ]
    ).get(
        'Reservations', []
    )

    instances = sum(
        [
            [i for i in r['Instances']]
            for r in reservations
        ], [])

    print "Found %d instances that need backing up" % len(instances)

    to_tag = collections.defaultdict(list)

    for instance in instances:
        try:
            retention_days = [
                int(t.get('Value')) for t in instance['Tags']
                if t['Key'] == 'Retention'][0]
        except IndexError:
            retention_days = 7

        for dev in instance['BlockDeviceMappings']:
            if dev.get('Ebs', None) is None:
                continue
            vol_id = dev['Ebs']['VolumeId']
            dev_name = dev['DeviceName']
            print "\tFound EBS volume %s (%s) on instance %s" % (
                vol_id, dev_name, instance['InstanceId'])

            # figure out instance name if there is one
            instance_name = ""
            for tag in instance['Tags']:
                if tag['Key'] != 'Name':
                    continue
                else:
                    instance_name = tag['Value']

            description = '%s - %s (%s)' % ( instance_name, vol_id, dev_name )

            # trigger snapshot
            snap = ec.create_snapshot(
                VolumeId=vol_id,
                Description=description
                )

            ec.create_tags(
                Resources=[snap['SnapshotId']],
                Tags=[{ 'Key': 'ParentInstance', 'Value': instance['InstanceId'] },
                      { 'Key': 'MountPoint', 'Value': dev['DeviceName'] },
                      { 'Key': 'Name', 'Value': instance_name + '_backup' }]
            )

            if (snap):
                print "\t\tSnapshot %s created in %s of [%s]" % ( snap['SnapshotId'], region, description )
            to_tag[retention_days].append(snap['SnapshotId'])
            print "\t\tRetaining snapshot %s of volume %s from instance %s (%s) for %d days" % (
                snap['SnapshotId'],
                vol_id,
                instance['InstanceId'],
                instance_name,
                retention_days,
            )

    for retention_days in to_tag.keys():
        delete_date = datetime.date.today() + datetime.timedelta(days=retention_days)
        delete_fmt = delete_date.strftime('%Y-%m-%d')
        print "Will delete %d snapshots on %s" % (len(to_tag[retention_days]), delete_fmt)
        ec.create_tags(
            Resources=to_tag[retention_days],
            Tags=[
                { 'Key': 'DeleteOn', 'Value': delete_fmt },
                { 'Key': 'Type', 'Value': 'Automated' },
            ]
        )

#!/usr/bin/env node

// VPC Diagnostic Tool for Lambda-RDS Connectivity Issues
// This script checks all potential networking issues

const AWS = require('aws-sdk');

// Configure AWS
const ec2 = new AWS.EC2({ region: 'us-east-1' });
const rds = new AWS.RDS({ region: 'us-east-1' });
const lambda = new AWS.Lambda({ region: 'us-east-1' });

async function diagnoseVPCIssues() {
    console.log('🔍 Lambda-RDS VPC Connectivity Diagnostic');
    console.log('==========================================');
    
    try {
        // Get Lambda configuration
        console.log('1. Getting Lambda configuration...');
        const lambdaConfig = await lambda.getFunctionConfiguration({
            FunctionName: 'financial-dashboard-api-dev'
        }).promise();
        
        console.log('📋 Lambda Configuration:');
        console.log(`   VPC ID: ${lambdaConfig.VpcConfig.VpcId}`);
        console.log(`   Subnets: ${lambdaConfig.VpcConfig.SubnetIds.join(', ')}`);
        console.log(`   Security Groups: ${lambdaConfig.VpcConfig.SecurityGroupIds.join(', ')}`);
        
        const vpcId = lambdaConfig.VpcConfig.VpcId;
        const lambdaSubnets = lambdaConfig.VpcConfig.SubnetIds;
        const lambdaSG = lambdaConfig.VpcConfig.SecurityGroupIds[0];
        
        // Check VPC details
        console.log('\\n2. Checking VPC details...');
        const vpcResult = await ec2.describeVpcs({
            VpcIds: [vpcId]
        }).promise();
        
        console.log('🌐 VPC Details:');
        console.log(`   CIDR: ${vpcResult.Vpcs[0].CidrBlock}`);
        console.log(`   DNS Support: ${vpcResult.Vpcs[0].EnableDnsSupport}`);
        console.log(`   DNS Hostnames: ${vpcResult.Vpcs[0].EnableDnsHostnames}`);
        
        // Check Lambda subnets
        console.log('\\n3. Checking Lambda subnets...');
        const subnetsResult = await ec2.describeSubnets({
            SubnetIds: lambdaSubnets
        }).promise();
        
        console.log('📡 Lambda Subnets:');
        for (const subnet of subnetsResult.Subnets) {
            console.log(`   ${subnet.SubnetId}:`);
            console.log(`     AZ: ${subnet.AvailabilityZone}`);
            console.log(`     CIDR: ${subnet.CidrBlock}`);
            console.log(`     Available IPs: ${subnet.AvailableIpAddressCount}`);
            console.log(`     Public: ${subnet.MapPublicIpOnLaunch}`);
        }
        
        // Check route tables
        console.log('\\n4. Checking route tables...');
        const routeTablesResult = await ec2.describeRouteTables({
            Filters: [
                {
                    Name: 'association.subnet-id',
                    Values: lambdaSubnets
                }
            ]
        }).promise();
        
        console.log('🛣️  Route Tables:');
        for (const routeTable of routeTablesResult.RouteTables) {
            console.log(`   ${routeTable.RouteTableId}:`);
            for (const route of routeTable.Routes) {
                console.log(`     ${route.DestinationCidrBlock || route.DestinationPrefixListId} -> ${route.GatewayId || route.NatGatewayId || route.NetworkInterfaceId || 'local'}`);
            }
        }
        
        // Check Lambda security group
        console.log('\\n5. Checking Lambda security group...');
        const sgResult = await ec2.describeSecurityGroups({
            GroupIds: [lambdaSG]
        }).promise();
        
        console.log('🔒 Lambda Security Group:');
        const sg = sgResult.SecurityGroups[0];
        console.log(`   ID: ${sg.GroupId}`);
        console.log(`   Name: ${sg.GroupName}`);
        console.log('   Outbound Rules:');
        for (const rule of sg.IpPermissionsEgress) {
            const protocol = rule.IpProtocol === '-1' ? 'All' : rule.IpProtocol;
            const port = rule.FromPort === rule.ToPort ? rule.FromPort : `${rule.FromPort}-${rule.ToPort}`;
            const destination = rule.IpRanges.length > 0 ? rule.IpRanges[0].CidrIp : 
                               rule.UserIdGroupPairs.length > 0 ? rule.UserIdGroupPairs[0].GroupId : 'Unknown';
            console.log(`     ${protocol}:${port} -> ${destination}`);
        }
        
        // Check RDS instances
        console.log('\\n6. Checking RDS instances...');
        const rdsResult = await rds.describeDBInstances().promise();
        
        console.log('🗄️  RDS Instances:');
        for (const instance of rdsResult.DBInstances) {
            if (instance.Endpoint && instance.Endpoint.Address.includes('stocks')) {
                console.log(`   ${instance.DBInstanceIdentifier}:`);
                console.log(`     Endpoint: ${instance.Endpoint.Address}:${instance.Endpoint.Port}`);
                console.log(`     VPC: ${instance.DBSubnetGroup.VpcId}`);
                console.log(`     Subnets: ${instance.DBSubnetGroup.Subnets.map(s => s.SubnetIdentifier).join(', ')}`);
                console.log(`     Security Groups: ${instance.VpcSecurityGroups.map(sg => sg.VpcSecurityGroupId).join(', ')}`);
                console.log(`     AZ: ${instance.AvailabilityZone}`);
                console.log(`     Public: ${instance.PubliclyAccessible}`);
                
                // Check RDS security groups
                for (const rdsSG of instance.VpcSecurityGroups) {
                    const rdsSGResult = await ec2.describeSecurityGroups({
                        GroupIds: [rdsSG.VpcSecurityGroupId]
                    }).promise();
                    
                    console.log(`     RDS Security Group ${rdsSG.VpcSecurityGroupId}:`);
                    const rdsSGDetails = rdsSGResult.SecurityGroups[0];
                    console.log('       Inbound Rules:');
                    for (const rule of rdsSGDetails.IpPermissions) {
                        const protocol = rule.IpProtocol === '-1' ? 'All' : rule.IpProtocol;
                        const port = rule.FromPort === rule.ToPort ? rule.FromPort : `${rule.FromPort}-${rule.ToPort}`;
                        const source = rule.IpRanges.length > 0 ? rule.IpRanges[0].CidrIp : 
                                     rule.UserIdGroupPairs.length > 0 ? rule.UserIdGroupPairs[0].GroupId : 'Unknown';
                        console.log(`         ${protocol}:${port} <- ${source}`);
                    }
                }
            }
        }
        
        // Check NAT Gateways
        console.log('\\n7. Checking NAT Gateways...');
        const natResult = await ec2.describeNatGateways({
            Filter: [
                {
                    Name: 'vpc-id',
                    Values: [vpcId]
                }
            ]
        }).promise();
        
        console.log('🌐 NAT Gateways:');
        if (natResult.NatGateways.length === 0) {
            console.log('   ❌ No NAT Gateways found! Lambda in private subnet needs NAT Gateway for internet access.');
        } else {
            for (const nat of natResult.NatGateways) {
                console.log(`   ${nat.NatGatewayId}:`);
                console.log(`     State: ${nat.State}`);
                console.log(`     Subnet: ${nat.SubnetId}`);
                console.log(`     Public IP: ${nat.NatGatewayAddresses[0]?.PublicIp || 'None'}`);
            }
        }
        
        // Check Internet Gateway
        console.log('\\n8. Checking Internet Gateway...');
        const igwResult = await ec2.describeInternetGateways({
            Filters: [
                {
                    Name: 'attachment.vpc-id',
                    Values: [vpcId]
                }
            ]
        }).promise();
        
        console.log('🌍 Internet Gateway:');
        if (igwResult.InternetGateways.length === 0) {
            console.log('   ❌ No Internet Gateway found! VPC needs internet access.');
        } else {
            for (const igw of igwResult.InternetGateways) {
                console.log(`   ${igw.InternetGatewayId}: ${igw.State}`);
            }
        }
        
        // Summary and recommendations
        console.log('\\n📋 DIAGNOSTIC SUMMARY & RECOMMENDATIONS:');
        console.log('=========================================');
        
        let criticalIssues = 0;
        let warnings = 0;
        
        // Check for common issues
        if (natResult.NatGateways.length === 0) {
            console.log('❌ CRITICAL: No NAT Gateway found');
            console.log('   Lambda in private subnet needs NAT Gateway to reach RDS');
            console.log('   Solution: Create NAT Gateway in public subnet and update route tables');
            criticalIssues++;
        }
        
        if (igwResult.InternetGateways.length === 0) {
            console.log('❌ CRITICAL: No Internet Gateway found');
            console.log('   VPC needs internet access for Lambda to work');
            console.log('   Solution: Create and attach Internet Gateway to VPC');
            criticalIssues++;
        }
        
        // Check if Lambda can reach RDS
        const lambdaAZs = subnetsResult.Subnets.map(s => s.AvailabilityZone);
        const rdsAZs = rdsResult.DBInstances
            .filter(db => db.Endpoint && db.Endpoint.Address.includes('stocks'))
            .map(db => db.AvailabilityZone);
        
        const commonAZs = lambdaAZs.filter(az => rdsAZs.includes(az));
        if (commonAZs.length === 0) {
            console.log('⚠️  WARNING: Lambda and RDS in different AZs');
            console.log('   This may cause connectivity issues');
            console.log('   Solution: Ensure Lambda subnets span same AZs as RDS');
            warnings++;
        }
        
        console.log(`\\n📊 Issues Found: ${criticalIssues} Critical, ${warnings} Warnings`);
        
        if (criticalIssues === 0 && warnings === 0) {
            console.log('✅ No obvious VPC connectivity issues found');
            console.log('   The problem may be in application code or credentials');
        }
        
    } catch (error) {
        console.error('❌ Diagnostic failed:', error);
        process.exit(1);
    }
}

// Run the diagnostic
diagnoseVPCIssues().catch(console.error);
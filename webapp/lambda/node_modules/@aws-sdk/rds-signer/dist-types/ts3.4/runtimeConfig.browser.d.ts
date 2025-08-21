import { SignerConfig } from "./Signer";
export declare const getRuntimeConfig: (config: SignerConfig) => {
  sha256: import("@smithy/types").HashConstructor;
  credentials:
    | import("@smithy/types").AwsCredentialIdentity
    | import("@smithy/types").AwsCredentialIdentityProvider
    | import("@smithy/types").Provider<any>;
  region: string | import("@smithy/types").Provider<any>;
  hostname: string;
  port: number;
  username: string;
  profile?: string;
  runtime: string;
};

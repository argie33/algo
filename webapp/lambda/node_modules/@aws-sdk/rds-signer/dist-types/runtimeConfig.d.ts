import type { SignerConfig } from "./Signer";
/**
 * @internal
 */
export declare const getRuntimeConfig: (config: SignerConfig) => {
    sha256: import("@smithy/types").HashConstructor;
    credentials: import("@smithy/types").AwsCredentialIdentity | import("@smithy/types").AwsCredentialIdentityProvider;
    region: string | import("@smithy/types").Provider<string>;
    hostname: string;
    port: number;
    username: string;
    profile?: string;
    runtime: string;
};

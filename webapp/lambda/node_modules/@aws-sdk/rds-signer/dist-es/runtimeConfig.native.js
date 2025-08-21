import { Sha256 } from "@aws-crypto/sha256-js";
import { invalidProvider } from "@smithy/invalid-dependency";
export const getRuntimeConfig = (config) => {
    return {
        runtime: "react-native",
        ...config,
        sha256: config?.sha256 ?? Sha256,
        credentials: config?.credentials ?? invalidProvider("Credential is missing"),
        region: config?.region ?? invalidProvider("Region is missing"),
    };
};

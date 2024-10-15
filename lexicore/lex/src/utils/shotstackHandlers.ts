import axios from "axios";

const endpoint = process.env.REACT_APP_SHOTSTACK_ENDPOINT ?? '';
const options = {
    headers: {
        'x-api-key': process.env.REACT_APP_SHOTSTACK_API_KEY
    }
}
const mockedData = {
    "timeline": {
        "tracks": [
            {
                "clips": [
                    {
                        "asset": {
                            "type": "text",
                            "text": "Welcome to Shotstack",
                            "font": {
                                "family": "Clear Sans",
                                "color": "#ffffff",
                                "size": 46
                            },
                            "alignment": {
                                "horizontal": "left"
                            },
                            "width": 566,
                            "height": 70
                        },
                        "start": 4,
                        "length": "end",
                        "transition": {
                            "in": "fade",
                            "out": "fade"
                        },
                        "offset": {
                            "x": -0.15,
                            "y": 0
                        },
                        "effect": "zoomIn"
                    }
                ]
            },
            {
                "clips": [
                    {
                        "asset": {
                            "type": "video",
                            "src": "https://shotstack-assets.s3-ap-southeast-2.amazonaws.com/footage/earth.mp4",
                            "trim": 5,
                            "volume": 1
                        },
                        "start": 0,
                        "length": "auto",
                        "transition": {
                            "in": "fade",
                            "out": "fade"
                        }
                    }
                ]
            },
            {
                "clips": [
                    {
                        "asset": {
                            "type": "audio",
                            "src": "https://shotstack-assets.s3-ap-southeast-2.amazonaws.com/music/freepd/motions.mp3",
                            "effect": "fadeOut",
                            "volume": 1
                        },
                        "start": 0,
                        "length": "end"
                    }
                ]
            }
        ]
    },
    "output": {
        "format": "mp4",
        "size": {
            "width": 1280,
            "height": 720
        }
    }
};

interface ShotstackCommonResponse <T> {
    success: boolean;
    response: T;
    message: string;
}

interface ShotstackGeneratedVideoResponse {
    id: string;
    message: string;
}
export const generateVideo = async (): Promise<string> => {
    const response = await axios.post<ShotstackCommonResponse<ShotstackGeneratedVideoResponse>, any>(endpoint, mockedData, options);
    if (response.data.success) {
        return response.data.response.id;
    }
    return Promise.reject(response.data.response);
}

interface ShotstackCheckStatusResponse {
    "id": string;
    "owner": string;
    "plan": "free";
    "status": "done";
    "url": string;
    "data": any;
    "created": Date;
    "updated": Date;
}

export const checkVideoStatus = async (id: string): Promise<ShotstackCheckStatusResponse> => {
    const response = await axios.get<ShotstackCommonResponse<ShotstackCheckStatusResponse>, any>(`${endpoint}/${id}`, options);
    if (response.data.success) {
        return response.data.response;
    }
    return Promise.reject(response.data.response);
}